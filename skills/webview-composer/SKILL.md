---
name: webview-composer
description: >
  WKWebView-based rich text email composer patterns. Activates when working on
  the email composition UI, contenteditable integration, formatting commands,
  image handling, or Swift↔JavaScript bridge code.
allowed-tools: Read, Write, Edit, Grep, Glob
---

# WKWebView Composer — UnleashedMail

## Architecture Overview

The email composer uses a WKWebView with a `contenteditable` div instead of native
NSAttributedString/NSTextView. This enables Gmail-compatible HTML output and rich
formatting without fighting AppKit text system limitations.

```
ComposeViewModel
  ↕ (async methods)
ComposerWebViewCoordinator (NSObject, WKScriptMessageHandler, WKNavigationDelegate)
  ↕ (JS bridge)
WKWebView (contenteditable HTML)
```

## Swift → JavaScript Communication

Use `evaluateJavaScript` for commands that return values:

```swift
func getComposerHTML() async throws -> String {
    try await webView.evaluateJavaScript(
        "document.getElementById('composer').innerHTML"
    ) as? String ?? ""
}

func execFormatCommand(_ command: String, value: String? = nil) {
    let escapedCommand = command.jsEscaped()
    let js: String
    if let value {
        let escapedValue = value.jsEscaped()
        js = "document.execCommand('\(escapedCommand)', false, '\(escapedValue)')"
    } else {
        js = "document.execCommand('\(escapedCommand)', false, null)"
    }
    webView.evaluateJavaScript(js)
}

// String extension for safe JS interpolation
private extension String {
    func jsEscaped() -> String {
        self.replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "'", with: "\\'")
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\r", with: "\\r")
    }
}
```

### Rules

1. **Always `await`** evaluateJavaScript when you need the return value.
2. **Sanitize interpolated values** — escape quotes in any user-provided strings.
3. **Batch commands** where possible to avoid round-trip overhead.

## JavaScript → Swift Communication

Use `WKScriptMessageHandler` — this is the **only** approved path for JS→Swift:

```swift
final class ComposerWebViewCoordinator: NSObject, WKScriptMessageHandler {
    func userContentController(
        _ controller: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard let body = message.body as? [String: Any],
              let event = body["event"] as? String else { return }

        switch event {
        case "contentChanged":
            let html = body["html"] as? String ?? ""
            viewModel.updateBody(html)
        case "imagePasted":
            let base64 = body["data"] as? String ?? ""
            Task { await viewModel.handlePastedImage(base64) }
        case "linkClicked":
            let url = body["url"] as? String ?? ""
            viewModel.handleLinkClick(url)
        default:
            break
        }
    }
}
```

Register the handler during WKWebView setup:

```swift
let config = WKWebViewConfiguration()
config.userContentController.add(coordinator, name: "unleashedMail")
```

And in the HTML/JS:

```javascript
window.webkit.messageHandlers.unleashedMail.postMessage({
    event: "contentChanged",
    html: document.getElementById("composer").innerHTML
});
```

### Rules

1. **Never use polling** (setInterval + evaluateJavaScript) to detect content changes.
2. **Use a MutationObserver** on the JS side to detect DOM changes and post messages.
3. **Type-check all message.body fields** — JS can send anything.

## HTML Template

The composer loads a local HTML file from the app bundle:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        #composer {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            font-size: 14px;
            line-height: 1.5;
            padding: 12px;
            outline: none;
            min-height: 200px;
        }
        #composer:empty::before {
            content: attr(data-placeholder);
            color: #999;
        }
    </style>
</head>
<body>
    <div id="composer" contenteditable="true" data-placeholder="Compose your email..."></div>
    <script src="composer.js"></script>
</body>
</html>
```

## Formatting Commands

Standard `document.execCommand` calls for toolbar buttons:

| Action     | Command          | Value         |
|-----------|------------------|---------------|
| Bold      | `bold`           | null          |
| Italic    | `italic`         | null          |
| Underline | `underline`      | null          |
| Link      | `createLink`     | URL string    |
| Unlink    | `unlink`         | null          |
| List (UL) | `insertUnorderedList` | null    |
| List (OL) | `insertOrderedList`   | null    |

Note: `execCommand` is technically deprecated but remains the most reliable cross-WebKit
approach for contenteditable formatting. Monitor for WebKit replacements.

## Image Handling

Images pasted or dragged into the composer:

1. JS intercepts the `paste` event, extracts clipboard image data as base64.
2. Posts to Swift via `unleashedMail` message handler.
3. Swift uploads to Gmail API (or stores locally as attachment).
4. Swift injects an `<img>` tag back via evaluateJavaScript with the final URL/CID.

## Testing the Composer

- Unit test the Coordinator's message handling with mock `WKScriptMessage` objects.
- Test HTML generation by calling `getComposerHTML()` after programmatic edits.
- Use XCUITest for end-to-end compose flow validation.
