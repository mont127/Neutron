// Neutron's window. Steam owns Play; this owns everything before that:
// which of your games are windows-only, and installing them.

import SwiftUI
import AppKit

// MARK: - model

struct Game: Identifiable, Hashable {
    let appid: String
    let name: String
    let verdict: String      // native-ok | windows-only | suspect | unknown
    var installed: Bool

    var id: String { appid }

    var isWindows: Bool { verdict == "windows-only" || verdict == "suspect" }

    var statusText: String {
        if verdict == "native-ok" { return "Native macOS" }
        if installed { return "Ready in Steam" }
        if verdict == "suspect" { return "Mac build looks stale" }
        return "Windows only"
    }

    var statusColor: Color {
        if verdict == "native-ok" { return .secondary }
        if installed { return .green }
        return .orange
    }
}

// MARK: - shelling out to the neutron script

final class Neutron: ObservableObject {
    @Published var games: [Game] = []
    @Published var busy = false
    @Published var busyAppid: String?
    @Published var playing: String?
    @Published var logLines: [String] = []
    @Published var loadFailed: String?

    let steamDir = ("~/Library/Application Support/Steam" as NSString).expandingTildeInPath
    let gamesDir = ("~/Library/Application Support/Neutron/games" as NSString).expandingTildeInPath

    var script: String {
        if let env = ProcessInfo.processInfo.environment["NEUTRON_SCRIPT"] { return env }
        let bundled = Bundle.main.bundlePath + "/Contents/Resources/installer/neutron"
        if FileManager.default.isExecutableFile(atPath: bundled) { return bundled }
        return (("~/Neutron-repo/neutron") as NSString).expandingTildeInPath
    }

    // the exe we installed for an appid, if any
    func exePath(_ appid: String) -> String? {
        let map = gamesDir + "/.map/" + appid
        if let s = try? String(contentsOfFile: map, encoding: .utf8) {
            let p = s.trimmingCharacters(in: .whitespacesAndNewlines)
            if !p.isEmpty && FileManager.default.isReadableFile(atPath: p) { return p }
        }
        return nil
    }

    func reload() {
        loadFailed = nil
        DispatchQueue.global().async {
            let out = self.run(self.script, ["scan-machine"])
            var parsed: [Game] = []
            for line in out.split(separator: "\n") {
                let f = line.split(separator: "|", omittingEmptySubsequences: false).map(String.init)
                guard f.count >= 5 else { continue }
                // installed for us means: we have a windows exe to launch
                let ours = self.exePath(f[0]) != nil
                parsed.append(Game(appid: f[0], name: f[4], verdict: f[1],
                                   installed: ours || (f[1] == "native-ok" && f[3] == "1")))
            }
            let sorted = parsed.sorted {
                if $0.isWindows != $1.isWindows { return $0.isWindows }
                return $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
            }
            DispatchQueue.main.async {
                self.games = sorted
                if sorted.isEmpty { self.loadFailed = "No games found. Is Steam installed and has it run at least once?" }
            }
        }
    }

    func install(_ game: Game) {
        guard !busy else { return }
        busy = true
        busyAppid = game.appid
        logLines = ["Getting \(game.name)…"]
        DispatchQueue.global().async {
            self.stream(self.script, ["get", game.appid]) { line in
                DispatchQueue.main.async {
                    self.logLines.append(line)
                    if self.logLines.count > 400 { self.logLines.removeFirst() }
                }
            }
            DispatchQueue.main.async {
                self.busy = false
                self.busyAppid = nil
                self.reload()
            }
        }
    }

    func play(_ game: Game) {
        guard let exe = exePath(game.appid) else { return }
        playing = game.appid
        logLines = ["Launching \(game.name)…"]
        DispatchQueue.global().async {
            let runner = ("~/Library/Application Support/Neutron/bin/neutron-run" as NSString).expandingTildeInPath
            self.stream(runner, [exe]) { line in
                DispatchQueue.main.async {
                    self.logLines.append(line)
                    if self.logLines.count > 400 { self.logLines.removeFirst() }
                }
            }
            DispatchQueue.main.async {
                self.playing = nil
                self.logLines.append("\(game.name) exited.")
            }
        }
    }

    func artwork(_ appid: String) -> NSImage? {
        let dir = steamDir + "/appcache/librarycache/" + appid
        for name in ["library_600x900_2x.jpg", "library_600x900.jpg", "header.jpg"] {
            let p = dir + "/" + name
            if let img = NSImage(contentsOfFile: p) { return img }
        }
        return nil
    }

    @discardableResult
    private func run(_ cmd: String, _ args: [String]) -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [cmd] + args
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = Pipe()
        do { try p.run() } catch { return "" }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return String(data: data, encoding: .utf8) ?? ""
    }

    private func stream(_ cmd: String, _ args: [String], _ onLine: @escaping (String) -> Void) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [cmd] + args
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        var buffer = ""
        pipe.fileHandleForReading.readabilityHandler = { h in
            let d = h.availableData
            guard !d.isEmpty, let s = String(data: d, encoding: .utf8) else { return }
            buffer += s
            while let nl = buffer.firstIndex(of: "\n") {
                let line = String(buffer[buffer.startIndex..<nl])
                buffer = String(buffer[buffer.index(after: nl)...])
                let clean = line.trimmingCharacters(in: .whitespacesAndNewlines)
                if !clean.isEmpty { onLine(clean) }
            }
        }
        do { try p.run() } catch { onLine("could not run \(cmd)"); return }
        p.waitUntilExit()
        pipe.fileHandleForReading.readabilityHandler = nil
    }
}

// MARK: - views

struct Cover: View {
    let image: NSImage?
    var body: some View {
        Group {
            if let image {
                Image(nsImage: image).resizable().aspectRatio(contentMode: .fill)
            } else {
                RoundedRectangle(cornerRadius: 6).fill(Color.secondary.opacity(0.18))
            }
        }
        .frame(width: 46, height: 66)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }
}

struct Row: View {
    let game: Game
    let art: NSImage?
    let busy: Bool
    let playing: Bool
    let onInstall: () -> Void
    let onPlay: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Cover(image: art)
            VStack(alignment: .leading, spacing: 3) {
                Text(game.name).font(.system(size: 13, weight: .medium)).lineLimit(1)
                Text(game.statusText).font(.system(size: 11)).foregroundStyle(game.statusColor)
            }
            Spacer()
            if game.verdict == "native-ok" {
                Text("Steam handles it").font(.system(size: 11)).foregroundStyle(.tertiary)
            } else if game.installed {
                if playing {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text("Running").font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                } else {
                    Button {
                        onPlay()
                    } label: {
                        Label("Play", systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent).controlSize(.small).tint(.green)
                }
            } else if busy {
                ProgressView().controlSize(.small)
            } else {
                Button("Install", action: onInstall).buttonStyle(.borderedProminent).controlSize(.small)
            }
        }
        .padding(.vertical, 5)
    }
}

struct ContentView: View {
    @StateObject private var n = Neutron()
    @State private var search = ""

    var windowsGames: [Game] { n.games.filter { $0.isWindows } }
    var macGames: [Game] { n.games.filter { !$0.isWindows } }

    func filtered(_ list: [Game]) -> [Game] {
        search.isEmpty ? list : list.filter { $0.name.localizedCaseInsensitiveContains(search) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Neutron").font(.system(size: 15, weight: .semibold))
                    Text("Windows games in your Steam library")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                }
                Spacer()
                TextField("Search", text: $search).textFieldStyle(.roundedBorder).frame(width: 170)
                Button { n.reload() } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(n.busy)
            }
            .padding(12)
            Divider()

            if let err = n.loadFailed {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle").font(.title2).foregroundStyle(.orange)
                    Text(err).font(.system(size: 12)).multilineTextAlignment(.center)
                }.frame(maxWidth: .infinity, maxHeight: .infinity).padding()
            } else {
                List {
                    if !filtered(windowsGames).isEmpty {
                        Section("Runs through Neutron") {
                            ForEach(filtered(windowsGames)) { g in
                                Row(game: g, art: n.artwork(g.appid),
                                    busy: n.busyAppid == g.appid,
                                    playing: n.playing == g.appid,
                                    onInstall: { n.install(g) },
                                    onPlay: { n.play(g) })
                            }
                        }
                    }
                    if !filtered(macGames).isEmpty {
                        Section("Native macOS — Steam runs these itself") {
                            ForEach(filtered(macGames)) { g in
                                Row(game: g, art: n.artwork(g.appid), busy: false,
                                    playing: false, onInstall: {}, onPlay: {})
                            }
                        }
                    }
                }
                .listStyle(.inset)
            }

            if n.busy || !n.logLines.isEmpty {
                Divider()
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 1) {
                            ForEach(Array(n.logLines.enumerated()), id: \.offset) { i, l in
                                Text(l).font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(.secondary).id(i)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }.padding(8)
                    }
                    .frame(height: 110)
                    .onChange(of: n.logLines.count) { _, c in
                        withAnimation { proxy.scrollTo(c - 1, anchor: .bottom) }
                    }
                }
            }
        }
        .frame(minWidth: 620, minHeight: 460)
        .onAppear { n.reload() }
    }
}

@main
struct NeutronApp: App {
    var body: some Scene {
        WindowGroup("Neutron") { ContentView() }
            .windowResizability(.contentSize)
    }
}
