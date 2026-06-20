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
                .frame(width: 520, height: 360)
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
    @Published var preserveClipboard = true
    @Published var pasteIntoActiveApp = true
    @Published var pushHotkey = "cmd+option"
    @Published var lockHotkey = "ctrl+cmd+option"
    @Published var statusText = "Checking service"
    @Published var healthText = "Not checked"
    @Published var lastCommandOutput = ""

    private var pollTimer: Timer?
    private var commandURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("bin")
            .appendingPathComponent("macos-local-asr")
    }

    var menuBarSymbol: String {
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
                self.modelLoaded = false
                self.statusText = "Service not reachable"
                self.lastCommandOutput = result.stderr.isEmpty ? result.stdout : result.stderr
                return
            }
            guard let data = result.stdout.data(using: .utf8),
                  let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                self.statusText = "Invalid service response"
                return
            }
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

    func runHealthCheck() {
        run(["health"]) { [weak self] result in
            self?.healthText = result.stdout.isEmpty ? result.stderr : result.stdout
        }
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
}

struct MenuContentView: View {
    @EnvironmentObject private var controller: ASRController
    @Environment(\.openSettings) private var openSettings

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HeaderView()

            Divider()

            VStack(spacing: 8) {
                if controller.isRecording {
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
                Button("Restart Worker") {
                    controller.restartWorker()
                }
                Spacer()
                Button("Quit") {
                    controller.quit()
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
            HealthSettingsView()
                .tabItem {
                    Label("Health", systemImage: "checkmark.seal")
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
            Button("Restart Worker") {
                controller.restartWorker()
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
            TextField("Push-to-talk hotkey", text: $pushHotkey)
            Button("Save Push-to-Talk Hotkey") {
                controller.setConfig("hotkey", value: pushHotkey)
            }

            TextField("Locked recording hotkey", text: $lockHotkey)
            Button("Save Locked Recording Hotkey") {
                controller.setConfig("lock_hotkey", value: lockHotkey)
            }

            Text("Use modifier-only values like cmd+option or ctrl+cmd+option. Restart after changing hotkeys.")
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
