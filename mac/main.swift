import Cocoa
import WebKit

/// Native shell: starts the bundled Python converter on a free local port and shows it in a window.
final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?
    private var serverReady = false
    private var stdoutBuffer = ""
    private var stderrBuffer = ""

    private let outDir = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Downloads/YT Converter", isDirectory: true)

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        buildWindow()
        startServer()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        server?.terminate()
    }

    // MARK: Window

    private func buildWindow() {
        let config = WKWebViewConfiguration()
        config.applicationNameForUserAgent = "LocalConverterApp"
        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.loadHTMLString(
            "<body style='font:15px -apple-system;color:#888;display:grid;place-items:center;height:90vh;background:transparent'>Starting…</body>",
            baseURL: nil)

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1040, height: 680),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        window.title = "Local Converter"
        window.contentView = webView
        window.contentMinSize = NSSize(width: 880, height: 580)
        window.setFrameAutosaveName("MainWindow.v2")
        if !window.setFrameUsingName("MainWindow.v2") { window.center() }
        window.makeKeyAndOrderFront(nil)
    }

    // MARK: Server

    private func findPython() -> String? {
        ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
            .first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    private func startServer() {
        guard let python = findPython() else {
            return fatal("Python 3 was not found. Install it with: brew install python")
        }
        guard let script = Bundle.main.path(forResource: "server", ofType: "py") else {
            return fatal("server.py is missing from the app bundle.")
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = ["-I", script]
        var env = ProcessInfo.processInfo.environment
        env["PORT"] = "0"
        env["WATCH_PARENT"] = "1"
        env["OUT_DIR"] = outDir.path
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        process.environment = env

        let out = Pipe(), err = Pipe()
        process.standardOutput = out
        process.standardError = err
        out.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async { self?.consumeStdout(text) }
        }
        err.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async { self?.stderrBuffer += text }
        }
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self, !self.serverReady else { return }
                let detail = self.stderrBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
                self.fatal(detail.isEmpty ? "The converter engine stopped unexpectedly." : detail)
            }
        }

        do {
            try process.run()
            server = process
        } catch {
            fatal("Could not start the converter engine: \(error.localizedDescription)")
        }
    }

    private func consumeStdout(_ text: String) {
        stdoutBuffer += text
        guard !serverReady,
              let line = stdoutBuffer.split(separator: "\n").first(where: { $0.hasPrefix("READY ") }),
              let address = line.dropFirst(6).split(separator: " ").first,
              let url = URL(string: String(address)) else { return }
        serverReady = true
        webView.load(URLRequest(url: url))
    }

    private func fatal(_ message: String) {
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = "Local Converter can't start"
        alert.informativeText = message
        alert.runModal()
        NSApp.terminate(nil)
    }

    // MARK: Navigation

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.allow) }
        if url.host == "127.0.0.1", url.path.hasPrefix("/files/") {
            // A finished conversion is already in ~/Downloads/YT Converter; reveal it instead of re-downloading.
            let name = URL(fileURLWithPath: url.path.removingPercentEncoding ?? "").lastPathComponent
            let file = outDir.appendingPathComponent(name)
            if FileManager.default.fileExists(atPath: file.path) {
                NSWorkspace.shared.activateFileViewerSelecting([file])
            }
            return decisionHandler(.cancel)
        }
        if let scheme = url.scheme, ["http", "https"].contains(scheme), url.host != "127.0.0.1" {
            NSWorkspace.shared.open(url)
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    // MARK: Menu

    @objc private func openDownloads() {
        try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        NSWorkspace.shared.open(outDir)
    }

    private func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem(); main.addItem(appItem)
        let appMenu = NSMenu(); appItem.submenu = appMenu
        appMenu.addItem(withTitle: "About Local Converter",
                        action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide Local Converter", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Local Converter", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        let fileItem = NSMenuItem(); main.addItem(fileItem)
        let fileMenu = NSMenu(title: "File"); fileItem.submenu = fileMenu
        let open = NSMenuItem(title: "Open Downloads Folder", action: #selector(openDownloads), keyEquivalent: "o")
        open.keyEquivalentModifierMask = [.command, .shift]
        open.target = self
        fileMenu.addItem(open)
        fileMenu.addItem(withTitle: "Close Window", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")

        let editItem = NSMenuItem(); main.addItem(editItem)
        let edit = NSMenu(title: "Edit"); editItem.submenu = edit
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = NSMenuItem(title: "Redo", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        edit.addItem(redo)
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        let windowItem = NSMenuItem(); main.addItem(windowItem)
        let windowMenu = NSMenu(title: "Window"); windowItem.submenu = windowMenu
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        NSApp.windowsMenu = windowMenu

        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
