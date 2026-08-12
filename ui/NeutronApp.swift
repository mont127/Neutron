// the installer window. you open it once; after that neutron lives inside
// steam and this app is never needed again.

import SwiftUI
import AppKit

enum Step: Equatable {
    case checking, notInstalled, steamOpen, working, done, failed(String)
}

final class Installer: ObservableObject {
    @Published var step: Step = .checking
    @Published var log: [String] = []
    @Published var windowsGames = 0
    @Published var enabledGames = 0
    @Published var steamRunning = false

    let home = NSHomeDirectory()
    var neutronHome: String { home + "/Library/Application Support/Neutron" }

    var script: String {
        if let e = ProcessInfo.processInfo.environment["NEUTRON_SCRIPT"] { return e }
        let bundled = Bundle.main.bundlePath + "/Contents/Resources/installer/neutron"
        if FileManager.default.isExecutableFile(atPath: bundled) { return bundled }
        return home + "/Neutron-repo/neutron"
    }

    // global defaults every game inherits unless its own Launch Options override
    @Published var backend = "d3dmetal"
    @Published var metalHUD = false
    @Published var msync = false      // known to crash-loop on this wine
    @Published var esync = true

    var defaultsPath: String { neutronHome + "/defaults" }

    func loadDefaults() {
        guard let t = try? String(contentsOfFile: defaultsPath, encoding: .utf8) else { return }
        for line in t.split(separator: "\n") {
            let kv = line.split(separator: "=", maxSplits: 1).map(String.init)
            guard kv.count == 2 else { continue }
            let v = kv[1].trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
            switch kv[0].replacingOccurrences(of: "export ", with: "") {
            case "MNC_GAME_BACKEND": backend = v
            case "NEUTRON_HUD": metalHUD = (v == "1")
            case "NEUTRON_MSYNC": msync = (v == "1")
            case "NEUTRON_ESYNC": esync = (v == "1")
            default: break
            }
        }
    }

    func saveDefaults() {
        let body = """
        export MNC_GAME_BACKEND=\(backend)
        export NEUTRON_HUD=\(metalHUD ? "1" : "0")
        export NEUTRON_MSYNC=\(msync ? "1" : "0")
        export NEUTRON_ESYNC=\(esync ? "1" : "0")
        """
        try? FileManager.default.createDirectory(atPath: neutronHome,
              withIntermediateDirectories: true)
        try? body.write(toFile: defaultsPath, atomically: true, encoding: .utf8)
    }

    var isInstalled: Bool {
        FileManager.default.fileExists(atPath: neutronHome + "/config")
    }

    func refresh() {
        steamRunning = !run("/usr/bin/pgrep", ["-x", "steam_osx"]).isEmpty
        let scan = run("/bin/bash", [script, "scan-machine"])
        var win = 0
        for line in scan.split(separator: "\n") {
            let f = line.split(separator: "|", omittingEmptySubsequences: false)
            if f.count >= 5 && f[2] == "neutron" { win += 1 }
        }
        windowsGames = win
        loadDefaults()
        if step == .checking { step = isInstalled ? .done : .notInstalled }
    }

    // quit steam if needed, apply, put steam back.
    func install(reopenSteam: Bool = true) {
        step = .working
        log = []
        DispatchQueue.global().async {
            let wasRunning = self.steamRunning
            if wasRunning {
                self.append("Closing Steam...")
                self.run("/usr/bin/osascript", ["-e", "tell application \"Steam\" to quit"])
                for _ in 0..<40 {
                    if self.run("/usr/bin/pgrep", ["-x", "steam_osx"]).isEmpty { break }
                    Thread.sleep(forTimeInterval: 1)
                }
            }
            self.stream("/bin/bash", [self.script, "apply"])
            if wasRunning && reopenSteam {
                self.append("Reopening Steam...")
                self.run("/usr/bin/open", ["-a", "Steam"])
            }
            DispatchQueue.main.async {
                self.step = self.isInstalled ? .done : .failed("Setup did not complete, see the log.")
                self.refresh()
            }
        }
    }

    private func append(_ s: String) {
        DispatchQueue.main.async {
            self.log.append(s)
            if self.log.count > 300 { self.log.removeFirst() }
        }
    }

    // the engine travels with the app as a zip. tell the installer where it is.
    private var childEnv: [String: String] {
        var e = ProcessInfo.processInfo.environment
        // __pycache__ written into our Resources breaks the bundle's signature
        e["PYTHONDONTWRITEBYTECODE"] = "1"
        let res = Bundle.main.bundlePath + "/Contents/Resources"
        let zip = res + "/wine-unified-bundle.zip"
        if FileManager.default.fileExists(atPath: zip) { e["NEUTRON_WINE_ZIP"] = zip }
        let dir = res + "/wine-unified"
        if FileManager.default.isExecutableFile(atPath: dir + "/loader/wine") {
            e["NEUTRON_BUNDLED_WINE"] = dir
        }
        return e
    }

    @discardableResult
    private func run(_ cmd: String, _ args: [String]) -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: cmd)
        p.arguments = args
        p.environment = childEnv
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = Pipe()
        do { try p.run() } catch { return "" }
        let d = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return String(data: d, encoding: .utf8) ?? ""
    }

    private func stream(_ cmd: String, _ args: [String]) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: cmd)
        p.arguments = args
        p.environment = childEnv
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        var buf = ""
        pipe.fileHandleForReading.readabilityHandler = { h in
            let d = h.availableData
            guard !d.isEmpty, let s = String(data: d, encoding: .utf8) else { return }
            buf += s
            while let nl = buf.firstIndex(of: "\n") {
                let line = String(buf[buf.startIndex..<nl]).trimmingCharacters(in: .whitespaces)
                buf = String(buf[buf.index(after: nl)...])
                if !line.isEmpty { self.append(line) }
            }
        }
        do { try p.run() } catch { append("could not run \(cmd)"); return }
        p.waitUntilExit()
        pipe.fileHandleForReading.readabilityHandler = nil
    }
}

struct Bullet: View {
    let text: String
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green).font(.system(size: 12))
            Text(text).font(.system(size: 12)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
    }
}

// drawn as a template so it turns white by itself in dark mode. falls back to
// a symbol in a checkout with no assets built.
struct LogoMark: View {
    var size: CGFloat = 52

    private var mark: NSImage? {
        guard let p = Bundle.main.path(forResource: "mark", ofType: "png"),
              let img = NSImage(contentsOfFile: p) else { return nil }
        img.isTemplate = true
        return img
    }

    var body: some View {
        if let img = mark {
            Image(nsImage: img)
                .resizable()
                .renderingMode(.template)
                .interpolation(.high)
                .frame(width: size, height: size)
                .foregroundStyle(.primary)
        } else {
            Image(systemName: "gamecontroller.fill")
                .font(.system(size: size * 0.65))
                .foregroundStyle(.tint)
        }
    }
}

struct ContentView: View {
    @StateObject private var m = Installer()

    var body: some View {
        VStack(spacing: 0) {
            VStack(spacing: 6) {
                LogoMark()
                Text("Neutron").font(.system(size: 22, weight: .semibold))
            }
            .frame(maxWidth: .infinity).padding(.top, 26).padding(.bottom, 18)

            Divider()

            VStack(alignment: .leading, spacing: 9) {
                switch m.step {
                case .done:
                    Label("Neutron is installed", systemImage: "checkmark.seal.fill")
                        .font(.system(size: 13, weight: .medium)).foregroundStyle(.green)
                    if m.steamRunning {
                        Text("Quit Steam once to finish enabling your games.")
                            .font(.system(size: 12)).foregroundStyle(.orange)
                    }

                    Divider().padding(.vertical, 4)
                    Text("Settings").font(.system(size: 12, weight: .semibold))
                    HStack {
                        Text("Graphics").font(.system(size: 12))
                        Spacer()
                        Picker("", selection: $m.backend) {
                            Text("D3DMetal").tag("d3dmetal")
                            Text("DXMT").tag("dxmt")
                            Text("DXVK").tag("dxvk")
                            Text("OpenGL").tag("opengl")
                        }
                        .labelsHidden().pickerStyle(.menu).frame(width: 130)
                        .onChange(of: m.backend) { _, _ in m.saveDefaults() }
                    }
                    Toggle("Metal performance HUD", isOn: $m.metalHUD)
                        .font(.system(size: 12))
                        .onChange(of: m.metalHUD) { _, _ in m.saveDefaults() }
                    Toggle("esync (recommended)", isOn: $m.esync)
                        .font(.system(size: 12))
                        .onChange(of: m.esync) { _, _ in m.saveDefaults() }
                    Toggle("msync (faster, but crashes many games here)", isOn: $m.msync)
                        .font(.system(size: 12))
                        .onChange(of: m.msync) { _, _ in m.saveDefaults() }
                    Text("Per game, override these in Steam \u{2192} Properties \u{2192} Launch Options, e.g. backend=dxmt hud=1")
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                default:
                    Text("This will set up Neutron so your Windows games get a working Install and Play button in Steam itself.")
                        .font(.system(size: 12)).fixedSize(horizontal: false, vertical: true)
                    Bullet(text: "Your Mac games are never touched.")
                    Bullet(text: "Steam does the downloading; Neutron runs the game.")
                    Bullet(text: "Nothing to open afterwards, this app is only needed once.")
                    if m.windowsGames > 0 {
                        Bullet(text: "\(m.windowsGames) Windows games found in your library.")
                    }
                }
            }
            .padding(16)

            if !m.log.isEmpty {
                Divider()
                ScrollViewReader { p in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 1) {
                            ForEach(Array(m.log.enumerated()), id: \.offset) { i, l in
                                Text(l).font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(.secondary).id(i)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }.padding(8)
                    }
                    .frame(height: 96)
                    .onChange(of: m.log.count) { _, c in withAnimation { p.scrollTo(c - 1, anchor: .bottom) } }
                }
            }

            Divider()
            HStack {
                if case .failed(let why) = m.step {
                    Text(why).font(.system(size: 11)).foregroundStyle(.red).lineLimit(2)
                }
                Spacer()
                if m.step == .working {
                    ProgressView().controlSize(.small)
                    Text("Working...").font(.system(size: 12)).foregroundStyle(.secondary)
                } else if m.step == .done {
                    Button("Re-apply") { m.install() }.controlSize(.large)
                    Button("Open Steam") {
                        NSWorkspace.shared.launchApplication("Steam")
                    }.buttonStyle(.borderedProminent).controlSize(.large)
                } else {
                    Button(m.step == .done ? "Re-apply" : "Install Neutron") { m.install() }
                        .buttonStyle(.borderedProminent).controlSize(.large)
                }
            }
            .padding(14)
        }
        .frame(width: 470)
        .onAppear { m.refresh() }
    }
}

@main
struct NeutronApp: App {
    var body: some Scene {
        WindowGroup("Neutron") { ContentView() }
            .windowResizability(.contentSize)
    }
}
