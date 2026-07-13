import Foundation
import AppKit
import Photos
import Vision

let visibleLibraryStillsSourceIdentifier = "visible-library-stills://v1"

func fetchSourceAssets(identifier: String) throws -> (PHFetchResult<PHAsset>, String) {
    if identifier == visibleLibraryStillsSourceIdentifier {
        let options = PHFetchOptions()
        options.includeHiddenAssets = false
        return (
            PHAsset.fetchAssets(with: .image, options: options),
            "Visible Apple Photos library - still photographs"
        )
    }
    guard let album = PHAssetCollection.fetchAssetCollections(
        withLocalIdentifiers: [identifier], options: nil
    ).firstObject else {
        throw ArchiveError.unresolved("album \(identifier)")
    }
    return (PHAsset.fetchAssets(in: album, options: nil), album.localizedTitle ?? "source")
}

struct PlanHeader: Codable {
    let operation: String?
}

struct FolderSpec: Codable {
    let key: String
    let title: String
    let parent_key: String?
    let existing_identifier: String?
}

struct AlbumSpec: Codable {
    let title: String
    let parent_folder_key: String
    let existing_identifier: String?
    let asset_identifiers: [String]
}

struct SnapshotPlan: Codable {
    let operation: String?
    let schema_version: Int
    let plan_id: String
    let safety_mode: String
    let source_album_identifier: String
    let expected_source_count: Int
    let batch_size: Int
    let log_path: String
    let receipt_path: String
    let folders: [FolderSpec]
    let albums: [AlbumSpec]
}

struct InspectionPlan: Codable {
    let operation: String
    let schema_version: Int
    let plan_id: String
    let safety_mode: String
    let source_album_identifier: String
    let expected_source_count: Int
    let asset_identifiers: [String]
    let output_jsonl_path: String
    let receipt_path: String
    let log_path: String
    let preview_directory: String
    let target_long_edge: Int
    let export_previews: Bool
    let ocr_all: Bool
    let classify_all: Bool?
    let detect_faces: Bool?
    let network_access_allowed: Bool
}

struct InspectionRow: Codable {
    let asset_identifier: String
    let pixel_available: Bool
    let preview_exported: Bool
    let pixel_width: Int
    let pixel_height: Int
    let media_subtype: UInt
    let favorite: Bool
    let hidden: Bool
    let ocr_text_length: Int
    let ocr_line_count: Int
    let vision_labels: [String]
    let vision_label_confidences: [Float]
    let detected_face_count: Int
    let safety_state: String
    let safety_flags: [String]
    let error: String?
}

struct InspectionReceipt: Codable {
    let completed_at: String
    let plan_id: String
    let source_album_identifier: String
    let source_count: Int
    let requested_count: Int
    let completed_count: Int
    let pixel_available_count: Int
    let preview_exported_count: Int
    let sensitive_hold_count: Int
    let unavailable_count: Int
    let resumed_count: Int
    let network_access_allowed: Bool
    let external_uploads_performed: Bool
}

struct FolderReceipt: Codable {
    let key: String
    let title: String
    let identifier: String
}

struct AlbumReceipt: Codable {
    let title: String
    let identifier: String
    let count: Int
}

struct SnapshotReceipt: Codable {
    let completed_at: String
    let plan_id: String
    let source_album_identifier: String
    let source_count: Int
    let safety_mode: String
    let folders: [FolderReceipt]
    let albums: [AlbumReceipt]
}

enum ArchiveError: Error, CustomStringConvertible {
    case usage
    case authorization(Int)
    case invalidPlan(String)
    case unresolved(String)
    case duplicate(String)
    case titleMismatch(String)
    case unexpectedMembership(String, Int)
    case membershipMismatch(String, Int, Int)
    case inspection(String)

    var description: String {
        switch self {
        case .usage:
            return "Usage: JamiePhotoArchive --plan /absolute/path/plan.json"
        case .authorization(let status):
            return "Full Photos access unavailable; authorization status=\(status)"
        case .invalidPlan(let reason):
            return "Invalid plan: \(reason)"
        case .unresolved(let object):
            return "Could not resolve \(object)"
        case .duplicate(let object):
            return "More than one protected object matched \(object)"
        case .titleMismatch(let object):
            return "Identifier resolved with an unexpected title: \(object)"
        case .unexpectedMembership(let album, let count):
            return "Album \(album) contains \(count) members outside the immutable plan"
        case .membershipMismatch(let album, let expected, let actual):
            return "Album \(album) membership mismatch: expected \(expected), actual \(actual)"
        case .inspection(let reason):
            return "Inspection failed: \(reason)"
        }
    }
}

final class InspectionRunner {
    private let plan: InspectionPlan
    private let imageManager = PHImageManager.default()
    private let encoder = JSONEncoder()

    init(plan: InspectionPlan) {
        self.plan = plan
        encoder.outputFormatting = [.sortedKeys]
    }

    func log(_ message: String) {
        let stamp = ISO8601DateFormatter().string(from: Date())
        let line = "[\(stamp)] plan=\(plan.plan_id) \(message)\n"
        print(line, terminator: "")
        let url = URL(fileURLWithPath: plan.log_path)
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: Data())
        }
        if let handle = try? FileHandle(forWritingTo: url) {
            defer { try? handle.close() }
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: Data(line.utf8))
        }
    }

    func run() throws -> InspectionReceipt {
        guard plan.schema_version == 1 else {
            throw ArchiveError.invalidPlan("unsupported inspection schema_version")
        }
        guard plan.operation == "inspect-local-images" else {
            throw ArchiveError.invalidPlan("unrecognized inspection operation")
        }
        guard plan.safety_mode == "read-only-local-inspection-and-preview-export" else {
            throw ArchiveError.invalidPlan("unrecognized inspection safety_mode")
        }
        guard plan.network_access_allowed == false else {
            throw ArchiveError.invalidPlan("network access must remain disabled")
        }
        guard (256...2400).contains(plan.target_long_edge) else {
            throw ArchiveError.invalidPlan("target_long_edge outside 256...2400")
        }
        let unique = Set(plan.asset_identifiers)
        guard unique.count == plan.asset_identifiers.count else {
            throw ArchiveError.invalidPlan("duplicate asset identifier in inspection plan")
        }
        guard unique.allSatisfy({ $0.hasSuffix("/L0/001") }) else {
            throw ArchiveError.invalidPlan("non-asset identifier in inspection plan")
        }

        try requireAuthorization()
        let (sourceFetch, sourceTitle) = try fetchSourceAssets(identifier: plan.source_album_identifier)
        guard sourceFetch.count == plan.expected_source_count else {
            throw ArchiveError.membershipMismatch(
                sourceTitle,
                plan.expected_source_count,
                sourceFetch.count
            )
        }
        var sourceIdentifiers = Set<String>()
        sourceFetch.enumerateObjects { asset, _, _ in
            sourceIdentifiers.insert(asset.localIdentifier)
        }
        let outsideSource = unique.subtracting(sourceIdentifiers)
        guard outsideSource.isEmpty else {
            throw ArchiveError.inspection("\(outsideSource.count) requested assets are outside source")
        }
        log("verified_source count=\(sourceFetch.count) requested=\(unique.count)")

        let outputURL = URL(fileURLWithPath: plan.output_jsonl_path)
        try FileManager.default.createDirectory(
            at: outputURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if !FileManager.default.fileExists(atPath: outputURL.path) {
            FileManager.default.createFile(atPath: outputURL.path, contents: Data())
        }
        let completed = try completedIdentifiers(at: outputURL)
        let outputHandle = try FileHandle(forWritingTo: outputURL)
        defer { try? outputHandle.close() }
        try outputHandle.seekToEnd()

        if plan.export_previews {
            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: plan.preview_directory),
                withIntermediateDirectories: true
            )
        }

        var completedCount = completed.count
        var pixelAvailableCount = 0
        var previewExportedCount = 0
        var sensitiveHoldCount = 0
        var unavailableCount = 0
        let fetch = PHAsset.fetchAssets(withLocalIdentifiers: plan.asset_identifiers, options: nil)
        guard fetch.count == plan.asset_identifiers.count else {
            throw ArchiveError.membershipMismatch("inspection fetch", plan.asset_identifiers.count, fetch.count)
        }

        var assetsByIdentifier: [String: PHAsset] = [:]
        fetch.enumerateObjects { asset, _, _ in assetsByIdentifier[asset.localIdentifier] = asset }

        for (index, identifier) in plan.asset_identifiers.enumerated() {
            if completed.contains(identifier) { continue }
            guard let asset = assetsByIdentifier[identifier] else {
                throw ArchiveError.unresolved("inspection asset \(identifier)")
            }
            let row = autoreleasepool { inspect(asset) }
            let data = try encoder.encode(row)
            try outputHandle.write(contentsOf: data)
            try outputHandle.write(contentsOf: Data([0x0A]))
            completedCount += 1
            if row.pixel_available { pixelAvailableCount += 1 } else { unavailableCount += 1 }
            if row.preview_exported { previewExportedCount += 1 }
            if row.safety_state == "hold" { sensitiveHoldCount += 1 }
            if completedCount % 100 == 0 || index + 1 == plan.asset_identifiers.count {
                try outputHandle.synchronize()
                log(
                    "inspection_progress completed=\(completedCount) total=\(plan.asset_identifiers.count) " +
                    "pixels=\(pixelAvailableCount) holds=\(sensitiveHoldCount)"
                )
            }
        }

        return InspectionReceipt(
            completed_at: ISO8601DateFormatter().string(from: Date()),
            plan_id: plan.plan_id,
            source_album_identifier: plan.source_album_identifier,
            source_count: sourceFetch.count,
            requested_count: plan.asset_identifiers.count,
            completed_count: completedCount,
            pixel_available_count: pixelAvailableCount,
            preview_exported_count: previewExportedCount,
            sensitive_hold_count: sensitiveHoldCount,
            unavailable_count: unavailableCount,
            resumed_count: completed.count,
            network_access_allowed: plan.network_access_allowed,
            external_uploads_performed: false
        )
    }

    private func requireAuthorization() throws {
        var status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        if status == .notDetermined {
            var resolved: PHAuthorizationStatus?
            PHPhotoLibrary.requestAuthorization(for: .readWrite) { resolved = $0 }
            let deadline = Date().addingTimeInterval(180)
            while resolved == nil && Date() < deadline {
                RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.1))
            }
            status = resolved ?? PHPhotoLibrary.authorizationStatus(for: .readWrite)
        }
        guard status == .authorized else { throw ArchiveError.authorization(status.rawValue) }
    }

    private func fetchAlbum(identifier: String) throws -> PHAssetCollection {
        guard let album = PHAssetCollection.fetchAssetCollections(
            withLocalIdentifiers: [identifier], options: nil
        ).firstObject else {
            throw ArchiveError.unresolved("album \(identifier)")
        }
        return album
    }

    private func completedIdentifiers(at url: URL) throws -> Set<String> {
        guard let contents = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        var identifiers = Set<String>()
        for line in contents.split(separator: "\n") {
            guard let data = line.data(using: .utf8),
                  let row = try? JSONDecoder().decode(InspectionRow.self, from: data) else {
                continue
            }
            identifiers.insert(row.asset_identifier)
        }
        return identifiers
    }

    private func inspect(_ asset: PHAsset) -> InspectionRow {
        guard let image = requestImage(for: asset), let cgImage = makeCGImage(image) else {
            return InspectionRow(
                asset_identifier: asset.localIdentifier,
                pixel_available: false,
                preview_exported: false,
                pixel_width: asset.pixelWidth,
                pixel_height: asset.pixelHeight,
                media_subtype: asset.mediaSubtypes.rawValue,
                favorite: asset.isFavorite,
                hidden: asset.isHidden,
                ocr_text_length: 0,
                ocr_line_count: 0,
                vision_labels: [],
                vision_label_confidences: [],
                detected_face_count: 0,
                safety_state: "unavailable",
                safety_flags: ["local pixels unavailable"],
                error: "No local image result; network access remained disabled"
            )
        }

        let previewExported = plan.export_previews ? exportPreview(cgImage, identifier: asset.localIdentifier) : false
        var labels: [String] = []
        var confidences: [Float] = []
        var textLines: [String] = []
        var faceCount = 0
        var errors: [String] = []

        if plan.classify_all ?? true {
            do {
                let request = VNClassifyImageRequest()
                try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
                let results = (request.results ?? []).filter { $0.confidence >= 0.05 }.prefix(20)
                labels = results.map { $0.identifier }
                confidences = results.map { $0.confidence }
            } catch {
                errors.append("classification unavailable")
            }
        }

        if plan.ocr_all {
            do {
                let request = VNRecognizeTextRequest()
                request.recognitionLevel = .fast
                request.usesLanguageCorrection = false
                try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
                textLines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            } catch {
                errors.append("text recognition unavailable")
            }
        }

        if plan.detect_faces ?? true {
            do {
                let request = VNDetectFaceRectanglesRequest()
                try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
                faceCount = request.results?.count ?? 0
            } catch {
                errors.append("face count unavailable")
            }
        }

        let recognizedText = textLines.joined(separator: " ")
        let flags = safetyFlags(text: recognizedText, labels: labels)
        return InspectionRow(
            asset_identifier: asset.localIdentifier,
            pixel_available: true,
            preview_exported: previewExported,
            pixel_width: asset.pixelWidth,
            pixel_height: asset.pixelHeight,
            media_subtype: asset.mediaSubtypes.rawValue,
            favorite: asset.isFavorite,
            hidden: asset.isHidden,
            ocr_text_length: recognizedText.count,
            ocr_line_count: textLines.count,
            vision_labels: labels,
            vision_label_confidences: confidences,
            detected_face_count: faceCount,
            safety_state: flags.isEmpty ? "clear-automated" : "hold",
            safety_flags: flags,
            error: errors.isEmpty ? nil : errors.joined(separator: "; ")
        )
    }

    private func requestImage(for asset: PHAsset) -> NSImage? {
        let options = PHImageRequestOptions()
        options.isSynchronous = true
        options.isNetworkAccessAllowed = plan.network_access_allowed
        options.deliveryMode = .highQualityFormat
        options.resizeMode = .fast
        let longEdge = CGFloat(plan.target_long_edge)
        let target: CGSize
        if asset.pixelWidth >= asset.pixelHeight {
            target = CGSize(width: longEdge, height: max(1, longEdge * CGFloat(asset.pixelHeight) / CGFloat(max(asset.pixelWidth, 1))))
        } else {
            target = CGSize(width: max(1, longEdge * CGFloat(asset.pixelWidth) / CGFloat(max(asset.pixelHeight, 1))), height: longEdge)
        }
        var result: NSImage?
        imageManager.requestImage(
            for: asset,
            targetSize: target,
            contentMode: .aspectFit,
            options: options
        ) { image, _ in result = image }
        return result
    }

    private func makeCGImage(_ image: NSImage) -> CGImage? {
        var rect = CGRect(origin: .zero, size: image.size)
        return image.cgImage(forProposedRect: &rect, context: nil, hints: nil)
    }

    private func exportPreview(_ image: CGImage, identifier: String) -> Bool {
        let safeName = identifier.replacingOccurrences(of: "/", with: "_") + ".jpg"
        let url = URL(fileURLWithPath: plan.preview_directory).appendingPathComponent(safeName)
        if previewIsDecodable(url) { return true }
        let bitmap = NSBitmapImageRep(cgImage: image)
        guard let data = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.82]) else {
            return false
        }
        guard NSBitmapImageRep(data: data) != nil else { return false }
        do {
            try data.write(to: url, options: .atomic)
            return previewIsDecodable(url)
        } catch {
            return false
        }
    }

    private func previewIsDecodable(_ url: URL) -> Bool {
        guard let data = try? Data(contentsOf: url), !data.isEmpty else { return false }
        return NSBitmapImageRep(data: data) != nil
    }

    private func safetyFlags(text: String, labels: [String]) -> [String] {
        let normalized = text.lowercased()
        let normalizedLabels = labels.joined(separator: " ").lowercased()
        var flags = Set<String>()
        let patterns: [(String, String)] = [
            ("possible identity document", #"\b(passport|driver'?s? license|identity card|identification card|date of birth|place of birth|nationality|document no\.?|social security)\b"#),
            ("possible private contact information", #"[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}"#),
            ("possible exact street address", #"\b\d{1,6}\s+[a-z0-9][a-z0-9 .'-]{2,45}\s(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|lane|ln\.?|drive|dr\.?)\b"#),
            ("possible credentials or account data", #"\b(password|passcode|api[ -]?key|secret key|account number|routing number|login|credential)\b"#),
            ("possible financial data", #"\b(invoice|billing|payment request|bank statement|credit card|donor list|subscriber list)\b"#),
            ("possible medical or private record", #"\b(medical record|therapy|diagnosis|patient|health record|prescription)\b"#),
            ("possible private correspondence", #"\b(confidential|privileged|legal review|customer data|resident record|guest record)\b"#)
        ]
        for (label, pattern) in patterns {
            if normalized.range(of: pattern, options: .regularExpression) != nil {
                flags.insert(label)
            }
        }
        let documentLabels = ["passport", "identity document", "credit card", "document", "printed page", "mail", "receipt", "computer screen"]
        if documentLabels.contains(where: { normalizedLabels.contains($0) }) && text.count >= 24 {
            flags.insert("document or screen requires visual review")
        }
        return flags.sorted()
    }
}

final class ArchiveRunner {
    private let library = PHPhotoLibrary.shared()
    private let plan: SnapshotPlan
    private var folderByKey: [String: PHCollectionList] = [:]

    init(plan: SnapshotPlan) {
        self.plan = plan
    }

    func log(_ message: String) {
        let stamp = ISO8601DateFormatter().string(from: Date())
        let line = "[\(stamp)] plan=\(plan.plan_id) \(message)\n"
        print(line, terminator: "")
        let url = URL(fileURLWithPath: plan.log_path)
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: Data())
        }
        if let handle = try? FileHandle(forWritingTo: url) {
            defer { try? handle.close() }
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: Data(line.utf8))
        }
    }

    func run() throws -> SnapshotReceipt {
        guard plan.schema_version == 1 else {
            throw ArchiveError.invalidPlan("unsupported schema_version")
        }
        guard plan.safety_mode == "create-folders-albums-and-add-membership-only" else {
            throw ArchiveError.invalidPlan("unrecognized safety_mode")
        }
        guard (1...2000).contains(plan.batch_size) else {
            throw ArchiveError.invalidPlan("batch_size outside 1...2000")
        }
        try requireAuthorization()
        let (sourceFetch, sourceTitle) = try fetchSourceAssets(identifier: plan.source_album_identifier)
        let sourceCount = sourceFetch.count
        guard sourceCount == plan.expected_source_count else {
            throw ArchiveError.membershipMismatch(
                sourceTitle,
                plan.expected_source_count,
                sourceCount
            )
        }
        log("verified_source count=\(sourceCount)")

        var folderReceipts: [FolderReceipt] = []
        for spec in plan.folders {
            let folder = try ensureFolder(spec)
            folderByKey[spec.key] = folder
            folderReceipts.append(
                FolderReceipt(
                    key: spec.key,
                    title: spec.title,
                    identifier: folder.localIdentifier
                )
            )
            log("verified_folder key=\(spec.key) id=\(folder.localIdentifier)")
        }

        var albumReceipts: [AlbumReceipt] = []
        for spec in plan.albums {
            guard let parent = folderByKey[spec.parent_folder_key] else {
                throw ArchiveError.invalidPlan(
                    "unknown parent folder key \(spec.parent_folder_key)"
                )
            }
            let album = try ensureAlbum(spec, parent: parent)
            try writeAlbum(spec, album: album)
            let count = PHAsset.fetchAssets(in: album, options: nil).count
            albumReceipts.append(
                AlbumReceipt(
                    title: spec.title,
                    identifier: album.localIdentifier,
                    count: count
                )
            )
        }

        return SnapshotReceipt(
            completed_at: ISO8601DateFormatter().string(from: Date()),
            plan_id: plan.plan_id,
            source_album_identifier: plan.source_album_identifier,
            source_count: sourceCount,
            safety_mode: plan.safety_mode,
            folders: folderReceipts,
            albums: albumReceipts
        )
    }

    private func requireAuthorization() throws {
        var status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        if status == .notDetermined {
            var resolved: PHAuthorizationStatus?
            PHPhotoLibrary.requestAuthorization(for: .readWrite) { newStatus in
                resolved = newStatus
            }
            let deadline = Date().addingTimeInterval(180)
            while resolved == nil && Date() < deadline {
                RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.1))
            }
            status = resolved ?? PHPhotoLibrary.authorizationStatus(for: .readWrite)
        }
        guard status == .authorized else {
            throw ArchiveError.authorization(status.rawValue)
        }
    }

    private func fetchFolder(identifier: String) throws -> PHCollectionList {
        guard let folder = PHCollectionList.fetchCollectionLists(
            withLocalIdentifiers: [identifier], options: nil
        ).firstObject else {
            throw ArchiveError.unresolved("folder \(identifier)")
        }
        return folder
    }

    private func fetchAlbum(identifier: String) throws -> PHAssetCollection {
        guard let album = PHAssetCollection.fetchAssetCollections(
            withLocalIdentifiers: [identifier], options: nil
        ).firstObject else {
            throw ArchiveError.unresolved("album \(identifier)")
        }
        return album
    }

    private func children(of parent: PHCollectionList?) -> [PHCollection] {
        let result: PHFetchResult<PHCollection>
        if let parent {
            result = PHCollection.fetchCollections(in: parent, options: nil)
        } else {
            result = PHCollection.fetchTopLevelUserCollections(with: nil)
        }
        var children: [PHCollection] = []
        result.enumerateObjects { child, _, _ in children.append(child) }
        return children
    }

    private func ensureFolder(_ spec: FolderSpec) throws -> PHCollectionList {
        let parent = try spec.parent_key.map { key -> PHCollectionList in
            guard let folder = folderByKey[key] else {
                throw ArchiveError.invalidPlan("folder \(spec.key) precedes parent \(key)")
            }
            return folder
        }
        if let identifier = spec.existing_identifier {
            let folder = try fetchFolder(identifier: identifier)
            guard folder.localizedTitle == spec.title else {
                throw ArchiveError.titleMismatch(spec.key)
            }
            return folder
        }

        let matches = children(of: parent).compactMap { $0 as? PHCollectionList }.filter {
            $0.localizedTitle == spec.title
        }
        if matches.count > 1 { throw ArchiveError.duplicate("folder \(spec.title)") }
        if let match = matches.first { return match }

        var identifier: String?
        try library.performChangesAndWait {
            let request = PHCollectionListChangeRequest.creationRequestForCollectionList(
                withTitle: spec.title
            )
            let placeholder = request.placeholderForCreatedCollectionList
            identifier = placeholder.localIdentifier
            if let parent {
                PHCollectionListChangeRequest(for: parent)?.addChildCollections(
                    [placeholder] as NSArray
                )
            } else {
                let topLevel = PHCollection.fetchTopLevelUserCollections(with: nil)
                PHCollectionListChangeRequest(
                    forTopLevelCollectionListUserCollections: topLevel
                )?.addChildCollections([placeholder] as NSArray)
            }
        }
        guard let identifier else { throw ArchiveError.unresolved("new folder \(spec.title)") }
        return try fetchFolder(identifier: identifier)
    }

    private func ensureAlbum(
        _ spec: AlbumSpec,
        parent: PHCollectionList
    ) throws -> PHAssetCollection {
        if let identifier = spec.existing_identifier {
            let album = try fetchAlbum(identifier: identifier)
            guard album.localizedTitle == spec.title else {
                throw ArchiveError.titleMismatch(spec.title)
            }
            return album
        }
        let matches = children(of: parent).compactMap { $0 as? PHAssetCollection }.filter {
            $0.localizedTitle == spec.title
        }
        if matches.count > 1 { throw ArchiveError.duplicate("album \(spec.title)") }
        if let match = matches.first { return match }

        var identifier: String?
        try library.performChangesAndWait {
            let request = PHAssetCollectionChangeRequest.creationRequestForAssetCollection(
                withTitle: spec.title
            )
            let placeholder = request.placeholderForCreatedAssetCollection
            identifier = placeholder.localIdentifier
            PHCollectionListChangeRequest(for: parent)?.addChildCollections(
                [placeholder] as NSArray
            )
        }
        guard let identifier else { throw ArchiveError.unresolved("new album \(spec.title)") }
        return try fetchAlbum(identifier: identifier)
    }

    private func membership(of album: PHAssetCollection) -> Set<String> {
        let result = PHAsset.fetchAssets(in: album, options: nil)
        var identifiers = Set<String>()
        result.enumerateObjects { asset, _, _ in identifiers.insert(asset.localIdentifier) }
        return identifiers
    }

    private func writeAlbum(_ spec: AlbumSpec, album: PHAssetCollection) throws {
        let expected = Set(spec.asset_identifiers)
        guard expected.count == spec.asset_identifiers.count else {
            throw ArchiveError.invalidPlan("duplicate UUID in \(spec.title)")
        }
        guard expected.allSatisfy({ $0.hasSuffix("/L0/001") }) else {
            throw ArchiveError.invalidPlan("non-asset identifier in \(spec.title)")
        }
        var current = membership(of: album)
        let unexpected = current.subtracting(expected)
        if !unexpected.isEmpty {
            throw ArchiveError.unexpectedMembership(spec.title, unexpected.count)
        }
        let missing = spec.asset_identifiers.filter { !current.contains($0) }
        for start in stride(from: 0, to: missing.count, by: plan.batch_size) {
            let stop = min(start + plan.batch_size, missing.count)
            let batch = Array(missing[start..<stop])
            let assets = PHAsset.fetchAssets(withLocalIdentifiers: batch, options: nil)
            guard assets.count == batch.count else {
                throw ArchiveError.membershipMismatch(spec.title, batch.count, assets.count)
            }
            try library.performChangesAndWait {
                PHAssetCollectionChangeRequest(for: album)?.addAssets(assets)
            }
            current = membership(of: album)
            let unresolved = Set(batch).subtracting(current)
            if !unresolved.isEmpty {
                throw ArchiveError.membershipMismatch(
                    spec.title,
                    expected.count,
                    current.count
                )
            }
            log("album=\(spec.title) verified=\(current.count) expected=\(expected.count)")
        }
        current = membership(of: album)
        guard current == expected else {
            throw ArchiveError.membershipMismatch(spec.title, expected.count, current.count)
        }
        log("album=\(spec.title) final_count=\(current.count) verified=true")
    }
}

func writeReceipt(_ receipt: SnapshotReceipt, to path: String) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let data = try encoder.encode(receipt)
    let url = URL(fileURLWithPath: path)
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    try data.write(to: url, options: .atomic)
}

do {
    let arguments = CommandLine.arguments
    guard let planIndex = arguments.firstIndex(of: "--plan"),
          arguments.indices.contains(planIndex + 1) else {
        throw ArchiveError.usage
    }
    let planURL = URL(fileURLWithPath: arguments[planIndex + 1])
    let planData = try Data(contentsOf: planURL)
    let header = try JSONDecoder().decode(PlanHeader.self, from: planData)
    if header.operation == "inspect-local-images" {
        let plan = try JSONDecoder().decode(InspectionPlan.self, from: planData)
        let runner = InspectionRunner(plan: plan)
        let receipt = try runner.run()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let receiptURL = URL(fileURLWithPath: plan.receipt_path)
        try FileManager.default.createDirectory(
            at: receiptURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try encoder.encode(receipt).write(to: receiptURL, options: .atomic)
        runner.log("completed receipt=\(plan.receipt_path)")
    } else {
        let plan = try JSONDecoder().decode(SnapshotPlan.self, from: planData)
        let runner = ArchiveRunner(plan: plan)
        let receipt = try runner.run()
        try writeReceipt(receipt, to: plan.receipt_path)
        runner.log("completed receipt=\(plan.receipt_path)")
    }
    exit(0)
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
