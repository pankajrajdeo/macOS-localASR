import AppKit
import SwiftUI

@main
struct LocalASRMenuBarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var controller = ASRController()

    var body: some Scene {
        MenuBarExtra {
            MenuContentView()
                .environmentObject(controller)
                .frame(width: 320)
                .onAppear {
                    controller.refreshAll()
                    controller.startPolling()
                }
        } label: {
            Label("LocalASR", systemImage: controller.menuBarSymbol)
        }
        .menuBarExtraStyle(.window)

        Settings {
            SettingsView()
                .environmentObject(controller)
                .frame(width: 640, height: 560)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
    }
}

struct CommandResult: Sendable {
    let status: Int32
    let stdout: String
    let stderr: String
}

@MainActor
final class ASRController: ObservableObject {
    @Published var isRecording = false
    @Published var isLocked = false
    @Published var modelLoaded = false
    @Published var serviceReachable = false
    @Published var preserveClipboard = true
    @Published var pasteIntoActiveApp = true
    @Published var cleanupEnabled = false
    @Published var cleanupProvider = "ollama"
    @Published var cleanupModel = ""
    @Published var cleanupAPIBase = "http://127.0.0.1:11434"
    @Published var cleanupAPIKey = ""
    @Published var cleanupPrompt = ""
    @Published var cleanupModels: [String] = []
    @Published var cleanupStatus = "Enhance mode is off."
    @Published var pushHotkey = "cmd+option"
    @Published var lockHotkey = "ctrl+cmd+option"
    @Published var statusText = "Checking service"
    @Published var healthText = "Not checked"
    @Published var historyText = "Search or load stats to view local dictation history."
    @Published var fileTranscriptionStatus = "Choose an audio/video file or paste a URL."
    @Published var fileTranscriptionText = ""
    @Published var fileTranscriptionProgress: Double?
    @Published var fileTranscriptionProgressText = ""
    @Published var fileTranscriptionIsRunning = false
    @Published var selectedFilePath = ""
    @Published var selectedOutputPath = ""
    @Published var lastCommandOutput = ""

    private var pollTimer: Timer?
    private var fileTranscriptionHadResult = false
    private var commandURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("bin")
            .appendingPathComponent("macos-local-asr")
    }

    var menuBarSymbol: String {
        if !serviceReachable {
            return "mic.slash.circle"
        }
        if isRecording {
            return isLocked ? "waveform.circle.fill" : "waveform.circle"
        }
        return modelLoaded ? "mic.circle" : "mic.slash.circle"
    }

    func startPolling() {
        guard pollTimer == nil else { return }
        pollTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.refreshStatus()
            }
        }
    }

    func refreshAll() {
        refreshConfig()
        refreshStatus()
    }

    func refreshConfig() {
        run(["config", "show"]) { [weak self] result in
            guard let self else { return }
            guard result.status == 0, let data = result.stdout.data(using: .utf8) else {
                self.statusText = "Config unavailable"
                return
            }
            if let config = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                self.preserveClipboard = config["preserve_clipboard"] as? Bool ?? true
                self.pasteIntoActiveApp = config["paste_into_active_app"] as? Bool ?? true
                self.cleanupEnabled = config["cleanup_enabled"] as? Bool ?? false
                self.cleanupProvider = config["cleanup_provider"] as? String ?? "ollama"
                self.cleanupModel = config["cleanup_model"] as? String ?? ""
                self.cleanupAPIBase = config["cleanup_api_base"] as? String ?? "http://127.0.0.1:11434"
                self.cleanupAPIKey = config["cleanup_api_key"] as? String ?? ""
                self.cleanupPrompt = config["cleanup_prompt"] as? String ?? ""
                self.pushHotkey = config["hotkey"] as? String ?? "cmd+option"
                self.lockHotkey = config["lock_hotkey"] as? String ?? "ctrl+cmd+option"
            }
        }
    }

    func refreshStatus() {
        run(["control", "status", "--json"]) { [weak self] result in
            guard let self else { return }
            if result.status != 0 {
                self.isRecording = false
                self.isLocked = false
                self.modelLoaded = false
                self.serviceReachable = false
                self.statusText = "Service not reachable"
                self.lastCommandOutput = result.stderr.isEmpty ? result.stdout : result.stderr
                return
            }
            guard let data = result.stdout.data(using: .utf8),
                  let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                self.statusText = "Invalid service response"
                return
            }
            self.serviceReachable = true
            self.isRecording = payload["recording"] as? Bool ?? false
            self.isLocked = payload["locked"] as? Bool ?? false
            self.modelLoaded = payload["model_loaded"] as? Bool ?? false
            if self.isRecording {
                self.statusText = self.isLocked ? "Locked recording" : "Recording"
            } else if self.modelLoaded {
                self.statusText = "Ready"
            } else {
                self.statusText = "Loading model"
            }
        }
    }

    func startRecording(locked: Bool) {
        var args = ["control", "start"]
        if locked {
            args.append("--locked")
        }
        if let bundleID = NSWorkspace.shared.frontmostApplication?.bundleIdentifier {
            args.append(contentsOf: ["--target-bundle-id", bundleID])
        }
        run(args) { [weak self] result in
            self?.lastCommandOutput = result.stdout.isEmpty ? result.stderr : result.stdout
            self?.refreshStatus()
        }
    }

    func stopRecording() {
        run(["control", "stop"]) { [weak self] result in
            self?.lastCommandOutput = result.stdout.isEmpty ? result.stderr : result.stdout
            self?.refreshStatus()
        }
    }

    func cancelRecording() {
        run(["control", "cancel"]) { [weak self] result in
            self?.lastCommandOutput = result.stdout.isEmpty ? result.stderr : result.stdout
            self?.refreshStatus()
        }
    }

    func restartWorker() {
        run(["restart"]) { [weak self] result in
            self?.lastCommandOutput = result.stdout.isEmpty ? result.stderr : result.stdout
            self?.refreshAll()
        }
    }

    func startWorker() {
        run(["start"]) { [weak self] result in
            self?.lastCommandOutput = result.stdout.isEmpty ? result.stderr : result.stdout
            self?.refreshAll()
        }
    }

    func stopWorker() {
        run(["stop"]) { [weak self] result in
            guard let self else { return }
            self.lastCommandOutput = result.stdout.isEmpty ? result.stderr : result.stdout
            self.isRecording = false
            self.isLocked = false
            self.modelLoaded = false
            self.serviceReachable = false
            self.statusText = "Service stopped"
        }
    }

    func quitAndStopWorker() {
        run(["stop"]) { _ in
            NSApp.terminate(nil)
        }
    }

    func runHealthCheck() {
        run(["health"]) { [weak self] result in
            self?.healthText = result.stdout.isEmpty ? result.stderr : result.stdout
        }
    }

    func searchHistory(query: String) {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let args = trimmed.isEmpty ? ["history", "stats"] : ["history", "search", trimmed, "--limit", "25"]
        run(args) { [weak self] result in
            self?.historyText = result.stdout.isEmpty ? result.stderr : result.stdout
        }
    }

    func loadHistoryStats() {
        run(["history", "stats"]) { [weak self] result in
            self?.historyText = result.stdout.isEmpty ? result.stderr : result.stdout
        }
    }

    func loadCleanupModels() {
        cleanupStatus = "Checking models..."
        run(["cleanup", "models", "--json"]) { [weak self] result in
            guard let self else { return }
            guard let data = result.stdout.data(using: .utf8),
                  let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                self.cleanupModels = []
                self.cleanupStatus = result.stderr.isEmpty ? "Model listing failed." : result.stderr
                return
            }
            let models = payload["models"] as? [String] ?? []
            self.cleanupModels = models
            if payload["ok"] as? Bool == true {
                self.cleanupStatus = models.isEmpty ? "No models found." : "\(models.count) model(s) available."
                if self.cleanupModel.isEmpty, let first = models.first {
                    self.cleanupModel = first
                    self.setConfig("cleanup_model", value: first)
                }
            } else {
                self.cleanupStatus = payload["error"] as? String ?? "Model listing failed."
            }
        }
    }

    func testCleanup(sample: String) {
        cleanupStatus = "Testing cleanup..."
        run(["cleanup", "test", sample]) { [weak self] result in
            self?.cleanupStatus = result.stdout.isEmpty ? result.stderr : result.stdout
        }
    }

    func openOllama() {
        DispatchQueue.global(qos: .utility).async {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
            process.arguments = ["-a", "Ollama"]
            try? process.run()
        }
    }

    func chooseTranscriptionFile() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = []
        if panel.runModal() == .OK, let url = panel.url {
            selectedFilePath = url.path
            if selectedOutputPath.isEmpty {
                selectedOutputPath = url.deletingLastPathComponent().appendingPathComponent("transcript.txt").path
            }
        }
    }

    func chooseTranscriptOutput() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "transcript.txt"
        if panel.runModal() == .OK, let url = panel.url {
            selectedOutputPath = url.path
        }
    }

    func transcribeFileOrURL(input: String, output: String, noCleanup: Bool) {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            fileTranscriptionStatus = "Choose a file or enter a URL first."
            return
        }
        fileTranscriptionStatus = "Starting transcription..."
        fileTranscriptionText = ""
        fileTranscriptionProgress = 0
        fileTranscriptionProgressText = "Starting"
        fileTranscriptionIsRunning = true
        fileTranscriptionHadResult = false

        var args = ["transcribe", isWebURL(trimmed) ? "url" : "file", trimmed, "--progress-json"]
        let outputPath = output.trimmingCharacters(in: .whitespacesAndNewlines)
        if !outputPath.isEmpty {
            args.append(contentsOf: ["--output", outputPath])
        }
        if noCleanup {
            args.append("--no-cleanup")
        }

        runStreaming(args) { [weak self] line in
            guard let self else { return }
            self.handleTranscriptionLine(line, fallbackOutputPath: outputPath)
        } completion: { [weak self] result in
            guard let self else { return }
            self.fileTranscriptionIsRunning = false
            if !self.fileTranscriptionHadResult {
                self.fileTranscriptionProgress = nil
                self.fileTranscriptionProgressText = ""
                self.fileTranscriptionStatus = result.stderr.isEmpty ? "Transcription failed." : result.stderr
            }
        }
    }

    private func handleTranscriptionLine(_ line: String, fallbackOutputPath: String) {
        guard let data = line.data(using: .utf8),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return
        }
        let type = payload["type"] as? String
        if type == "progress" {
            let value = payload["progress"] as? Double ?? fileTranscriptionProgress ?? 0
            fileTranscriptionProgress = min(max(value, 0), 1)
            let message = payload["message"] as? String ?? "Working"
            if let current = payload["current"] as? Int, let total = payload["total"] as? Int, total > 1 {
                fileTranscriptionProgressText = "\(message) (\(current)/\(total))"
            } else {
                fileTranscriptionProgressText = message
            }
            fileTranscriptionStatus = fileTranscriptionProgressText
            return
        }

        if type == "result" || payload["ok"] != nil {
            fileTranscriptionHadResult = true
            fileTranscriptionIsRunning = false
            if payload["ok"] as? Bool == true {
                fileTranscriptionProgress = 1
                fileTranscriptionText = payload["text"] as? String ?? ""
                selectedOutputPath = payload["output_path"] as? String ?? fallbackOutputPath
                fileTranscriptionStatus = "Wrote \(selectedOutputPath)"
                fileTranscriptionProgressText = "Complete"
            } else {
                fileTranscriptionProgress = nil
                fileTranscriptionProgressText = ""
                fileTranscriptionStatus = payload["error"] as? String ?? "Transcription failed."
            }
        }
    }

    private func isWebURL(_ value: String) -> Bool {
        guard let url = URL(string: value), let scheme = url.scheme?.lowercased() else {
            return false
        }
        return (scheme == "http" || scheme == "https") && url.host != nil
    }

    func setConfig(_ key: String, value: String) {
        run(["config", "set", key, value]) { [weak self] result in
            self?.lastCommandOutput = result.stdout.isEmpty ? result.stderr : result.stdout
            self?.refreshConfig()
        }
    }

    func openPermissions() {
        let urls = [
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
        ]
        for value in urls {
            if let url = URL(string: value) {
                NSWorkspace.shared.open(url)
            }
        }
    }

    func quit() {
        NSApp.terminate(nil)
    }

    private func run(_ arguments: [String], completion: @escaping @MainActor @Sendable (CommandResult) -> Void) {
        let url = commandURL
        DispatchQueue.global(qos: .utility).async {
            let process = Process()
            process.executableURL = url
            process.arguments = arguments

            let output = Pipe()
            let error = Pipe()
            process.standardOutput = output
            process.standardError = error

            do {
                try process.run()
                process.waitUntilExit()
                let stdout = String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                let stderr = String(data: error.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                let result = CommandResult(status: process.terminationStatus, stdout: stdout, stderr: stderr)
                Task { @MainActor in
                    completion(result)
                }
            } catch {
                let result = CommandResult(status: 1, stdout: "", stderr: error.localizedDescription)
                Task { @MainActor in
                    completion(result)
                }
            }
        }
    }

    private func runStreaming(
        _ arguments: [String],
        onStdoutLine: @escaping @MainActor (String) -> Void,
        completion: @escaping @MainActor (CommandResult) -> Void
    ) {
        let url = commandURL
        DispatchQueue.global(qos: .utility).async {
            let process = Process()
            process.executableURL = url
            process.arguments = arguments

            let output = Pipe()
            let error = Pipe()
            process.standardOutput = output
            process.standardError = error

            var stdout = ""
            var lineBuffer = ""

            func emitCompleteLines(_ text: String) {
                lineBuffer += text
                while let newline = lineBuffer.firstIndex(of: "\n") {
                    let line = String(lineBuffer[..<newline])
                    lineBuffer.removeSubrange(...newline)
                    Task { @MainActor in
                        onStdoutLine(line)
                    }
                }
            }

            do {
                try process.run()
                while true {
                    let data = output.fileHandleForReading.availableData
                    if data.isEmpty {
                        break
                    }
                    let chunk = String(data: data, encoding: .utf8) ?? ""
                    stdout += chunk
                    emitCompleteLines(chunk)
                }
                process.waitUntilExit()
                if !lineBuffer.isEmpty {
                    let line = lineBuffer
                    lineBuffer = ""
                    Task { @MainActor in
                        onStdoutLine(line)
                    }
                }
                let stderr = String(data: error.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                let result = CommandResult(status: process.terminationStatus, stdout: stdout, stderr: stderr)
                Task { @MainActor in
                    completion(result)
                }
            } catch {
                let result = CommandResult(status: 1, stdout: "", stderr: error.localizedDescription)
                Task { @MainActor in
                    completion(result)
                }
            }
        }
    }
}

struct MenuContentView: View {
    @EnvironmentObject private var controller: ASRController
    @Environment(\.openSettings) private var openSettings

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HeaderView()

            Divider()

            VStack(spacing: 8) {
                if !controller.serviceReachable {
                    Button {
                        controller.startWorker()
                    } label: {
                        Label("Start Service", systemImage: "play.circle")
                    }
                } else if controller.isRecording {
                    Button {
                        controller.stopRecording()
                    } label: {
                        Label("Stop and Paste", systemImage: "stop.circle.fill")
                    }
                    Button {
                        controller.cancelRecording()
                    } label: {
                        Label("Cancel Recording", systemImage: "xmark.circle")
                    }
                } else {
                    Button {
                        controller.startRecording(locked: true)
                    } label: {
                        Label("Start Locked Recording", systemImage: "record.circle")
                    }
                    Button {
                        controller.startRecording(locked: false)
                    } label: {
                        Label("Start Manual Recording", systemImage: "mic")
                    }
                }
            }

            Divider()

            Toggle("Preserve Clipboard", isOn: Binding(
                get: { controller.preserveClipboard },
                set: { controller.setConfig("preserve_clipboard", value: $0 ? "true" : "false") }
            ))

            Toggle("Paste Into Active App", isOn: Binding(
                get: { controller.pasteIntoActiveApp },
                set: { controller.setConfig("paste_into_active_app", value: $0 ? "true" : "false") }
            ))

            Divider()

            Button {
                controller.runHealthCheck()
            } label: {
                Label("Run Health Check", systemImage: "stethoscope")
            }

            Button {
                controller.openPermissions()
            } label: {
                Label("Open Permissions", systemImage: "lock.shield")
            }

            SettingsLink {
                Label("Settings", systemImage: "gearshape")
            }

            Divider()

            HStack {
                Button("Restart") {
                    controller.restartWorker()
                }
                Spacer()
                Button("Stop Service") {
                    controller.stopWorker()
                }
            }

            HStack {
                Button("Quit App") {
                    controller.quit()
                }
                Spacer()
                Button("Stop & Quit") {
                    controller.quitAndStopWorker()
                }
            }
        }
        .padding(16)
    }
}

struct HeaderView: View {
    @EnvironmentObject private var controller: ASRController

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: controller.menuBarSymbol)
                    .foregroundStyle(controller.isRecording ? .blue : .secondary)
                Text("LocalASR")
                    .font(.headline)
                Spacer()
                Text(controller.statusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text("Push: \(controller.pushHotkey)   Lock: \(controller.lockHotkey)")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var controller: ASRController

    var body: some View {
        TabView {
            GeneralSettingsView()
                .tabItem {
                    Label("General", systemImage: "slider.horizontal.3")
                }
            HotkeySettingsView()
                .tabItem {
                    Label("Hotkeys", systemImage: "keyboard")
                }
            EnhanceSettingsView()
                .tabItem {
                    Label("Enhance", systemImage: "sparkles")
                }
            TranscribeSettingsView()
                .tabItem {
                    Label("Transcribe", systemImage: "doc.text.magnifyingglass")
                }
            HealthSettingsView()
                .tabItem {
                    Label("Health", systemImage: "checkmark.seal")
                }
            HistorySettingsView()
                .tabItem {
                    Label("History", systemImage: "clock.arrow.circlepath")
                }
        }
        .padding()
        .onAppear {
            controller.refreshAll()
        }
    }
}

struct GeneralSettingsView: View {
    @EnvironmentObject private var controller: ASRController

    var body: some View {
        Form {
            Toggle("Preserve clipboard after paste", isOn: Binding(
                get: { controller.preserveClipboard },
                set: { controller.setConfig("preserve_clipboard", value: $0 ? "true" : "false") }
            ))
            Toggle("Paste transcript into active app", isOn: Binding(
                get: { controller.pasteIntoActiveApp },
                set: { controller.setConfig("paste_into_active_app", value: $0 ? "true" : "false") }
            ))
            HStack {
                Button("Start Service") {
                    controller.startWorker()
                }
                Button("Stop Service") {
                    controller.stopWorker()
                }
                Button("Restart Service") {
                    controller.restartWorker()
                }
            }
        }
        .formStyle(.grouped)
    }
}

struct HotkeySettingsView: View {
    @EnvironmentObject private var controller: ASRController
    @State private var pushHotkey = ""
    @State private var lockHotkey = ""

    var body: some View {
        Form {
            VStack(alignment: .leading, spacing: 8) {
                TextField("Push-to-talk hotkey", text: $pushHotkey)
                HStack {
                    Button("Save Push-to-Talk Hotkey") {
                        controller.setConfig("hotkey", value: pushHotkey)
                    }
                    HotkeyRecorderButton(title: "Record Push Hotkey") { value in
                        pushHotkey = value
                        controller.setConfig("hotkey", value: value)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                TextField("Locked recording hotkey", text: $lockHotkey)
                HStack {
                    Button("Save Locked Recording Hotkey") {
                        controller.setConfig("lock_hotkey", value: lockHotkey)
                    }
                    HotkeyRecorderButton(title: "Record Lock Hotkey") { value in
                        lockHotkey = value
                        controller.setConfig("lock_hotkey", value: value)
                    }
                }
            }

            Text("Use Command, Option, and Control combinations. Restart the service after changing hotkeys.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .formStyle(.grouped)
        .onAppear {
            pushHotkey = controller.pushHotkey
            lockHotkey = controller.lockHotkey
        }
    }
}

struct HotkeyRecorderButton: View {
    let title: String
    let onRecord: (String) -> Void
    @State private var isRecording = false
    @State private var monitor: Any?
    @State private var pendingValue = ""
    @State private var finalizeTimer: Timer?

    var body: some View {
        Button(isRecording ? (pendingValue.isEmpty ? "Press modifiers..." : "Recording: \(pendingValue)") : title) {
            isRecording ? stopRecording() : startRecording()
        }
        .onDisappear {
            stopRecording()
        }
    }

    private func startRecording() {
        stopRecording()
        isRecording = true
        pendingValue = ""
        monitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { event in
            let value = hotkeyString(from: event.modifierFlags)
            if !value.isEmpty {
                pendingValue = value
                finalizeTimer?.invalidate()
                finalizeTimer = Timer.scheduledTimer(withTimeInterval: 0.45, repeats: false) { _ in
                    Task { @MainActor in
                        onRecord(value)
                        stopRecording()
                    }
                }
            }
            return event
        }
    }

    private func stopRecording() {
        if let monitor {
            NSEvent.removeMonitor(monitor)
            self.monitor = nil
        }
        finalizeTimer?.invalidate()
        finalizeTimer = nil
        pendingValue = ""
        isRecording = false
    }

    private func hotkeyString(from flags: NSEvent.ModifierFlags) -> String {
        var keys: [String] = []
        if flags.contains(.control) {
            keys.append("ctrl")
        }
        if flags.contains(.command) {
            keys.append("cmd")
        }
        if flags.contains(.option) {
            keys.append("option")
        }
        return keys.joined(separator: "+")
    }
}

struct EnhanceSettingsView: View {
    @EnvironmentObject private var controller: ASRController
    @State private var sampleText = "this is a sample dictation with missing punctuation"
    @State private var draftAPIBase = ""
    @State private var draftAPIKey = ""
    @State private var draftModel = ""
    @State private var draftPrompt = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Toggle("Enable ASR cleanup", isOn: Binding(
                get: { controller.cleanupEnabled },
                set: { controller.setConfig("cleanup_enabled", value: $0 ? "true" : "false") }
            ))

            Picker("Provider", selection: Binding(
                get: { controller.cleanupProvider },
                set: { value in
                    controller.setConfig("cleanup_provider", value: value)
                    if value == "ollama", controller.cleanupAPIBase.isEmpty {
                        controller.setConfig("cleanup_api_base", value: "http://127.0.0.1:11434")
                    }
                }
            )) {
                Text("Ollama local").tag("ollama")
                Text("OpenAI-compatible API").tag("openai_compatible")
            }
            .pickerStyle(.segmented)

            HStack {
                TextField("API base", text: $draftAPIBase)
                if controller.cleanupProvider == "ollama" {
                    Button("Open Ollama") {
                        controller.openOllama()
                    }
                    Button("Refresh Models") {
                        controller.loadCleanupModels()
                    }
                }
                Button("Save") {
                    controller.setConfig("cleanup_api_base", value: draftAPIBase)
                }
            }

            if controller.cleanupProvider == "openai_compatible" {
                HStack {
                    SecureField("API key", text: $draftAPIKey)
                    Button("Save Key") {
                        controller.setConfig("cleanup_api_key", value: draftAPIKey)
                    }
                }
                Text("API keys are currently stored in the local config file. Use a local server or throwaway key until Keychain storage is added.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if controller.cleanupProvider == "ollama", !controller.cleanupModels.isEmpty {
                Picker("Model", selection: Binding(
                    get: { controller.cleanupModel },
                    set: { value in
                        draftModel = value
                        controller.setConfig("cleanup_model", value: value)
                    }
                )) {
                    ForEach(controller.cleanupModels, id: \.self) { model in
                        Text(model).tag(model)
                    }
                }
            } else {
                HStack {
                    TextField("Model", text: $draftModel)
                    Button("Save Model") {
                        controller.setConfig("cleanup_model", value: draftModel)
                    }
                }
            }

            HStack {
                Text("Cleanup prompt")
                    .font(.headline)
                Spacer()
                Button("Save Prompt") {
                    controller.setConfig("cleanup_prompt", value: draftPrompt)
                }
            }
            TextEditor(text: $draftPrompt)
            .font(.system(.caption, design: .monospaced))
            .frame(minHeight: 110)

            HStack {
                TextField("Sample text", text: $sampleText)
                Button("Test") {
                    controller.testCleanup(sample: sampleText)
                }
            }

            Text(controller.cleanupStatus)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
        .onAppear {
            syncDrafts()
            if controller.cleanupProvider == "ollama" {
                controller.loadCleanupModels()
            }
        }
    }

    private func syncDrafts() {
        draftAPIBase = controller.cleanupAPIBase
        draftAPIKey = controller.cleanupAPIKey
        draftModel = controller.cleanupModel
        draftPrompt = controller.cleanupPrompt
    }
}

struct TranscribeSettingsView: View {
    @EnvironmentObject private var controller: ASRController
    @State private var input = ""
    @State private var output = ""
    @State private var noCleanup = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                TextField("Audio file path or YouTube/direct media URL", text: $input)
                Button("Browse...") {
                    controller.chooseTranscriptionFile()
                    input = controller.selectedFilePath
                    output = controller.selectedOutputPath
                }
            }

            HStack {
                TextField("Output transcript path", text: $output)
                Button("Save As...") {
                    controller.chooseTranscriptOutput()
                    output = controller.selectedOutputPath
                }
            }

            Toggle("Disable cleanup for this file", isOn: $noCleanup)

            HStack {
                Button("Transcribe") {
                    controller.transcribeFileOrURL(input: input, output: output, noCleanup: noCleanup)
                }
                .disabled(controller.fileTranscriptionIsRunning)
                Button("Reveal Transcript") {
                    if !controller.selectedOutputPath.isEmpty {
                        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: controller.selectedOutputPath)])
                    }
                }
                .disabled(controller.selectedOutputPath.isEmpty || controller.fileTranscriptionIsRunning)
            }

            if let progress = controller.fileTranscriptionProgress {
                VStack(alignment: .leading, spacing: 6) {
                    ProgressView(value: progress)
                    Text(controller.fileTranscriptionProgressText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            Text(controller.fileTranscriptionStatus)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)

            ScrollView {
                Text(controller.fileTranscriptionText)
                    .font(.system(.caption, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
        }
        .onAppear {
            input = controller.selectedFilePath
            output = controller.selectedOutputPath
        }
    }
}

struct HealthSettingsView: View {
    @EnvironmentObject private var controller: ASRController

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button("Run Health Check") {
                controller.runHealthCheck()
            }
            ScrollView {
                Text(controller.healthText)
                    .font(.system(.caption, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
        }
    }
}

struct HistorySettingsView: View {
    @EnvironmentObject private var controller: ASRController
    @State private var query = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                TextField("Search history", text: $query)
                Button("Search") {
                    controller.searchHistory(query: query)
                }
                Button("Stats") {
                    controller.loadHistoryStats()
                }
            }
            ScrollView {
                Text(controller.historyText)
                    .font(.system(.caption, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
        }
        .onAppear {
            controller.loadHistoryStats()
        }
    }
}
