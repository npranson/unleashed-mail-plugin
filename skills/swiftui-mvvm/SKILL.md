---
name: swiftui-mvvm
description: >
  SwiftUI + AppKit hybrid architecture patterns for UnleashedMail. Activates when
  building UI components, creating views or view models, or working on navigation,
  state management, or AppKit/SwiftUI bridging.
allowed-tools: Read, Write, Edit, Grep, Glob
---

# SwiftUI MVVM Patterns — UnleashedMail

## Architecture Layers

```
View (SwiftUI/AppKit)
  ↓ @StateObject / @ObservedObject
ViewModel (@Observable or ObservableObject)
  ↓ async calls
Service (protocol-based)
  ↓
Repository / GRDB layer
```

## ViewModel Conventions

Use `@Observable` (macOS 14+) for new ViewModels. Fall back to `ObservableObject` only when interfacing with older AppKit code.

```swift
import Observation

@Observable
final class ComposeViewModel {
    var to: String = ""
    var subject: String = ""
    var body: String = ""
    var isSending = false
    var error: ComposeError?

    private let emailService: EmailServiceProtocol

    init(emailService: EmailServiceProtocol) {
        self.emailService = emailService
    }

    func send() async {
        isSending = true
        defer { isSending = false }
        do {
            let draft = Draft(to: to, subject: subject, body: body)
            try await emailService.send(draft)
        } catch {
            self.error = .sendFailed(underlying: error)
        }
    }
}
```

### Rules for ViewModels

1. **No `import SwiftUI`** in ViewModel files. ViewModels depend on Foundation and domain types only.
2. **All external dependencies injected via init** — never construct services inside the ViewModel.
3. **Public properties are the view's data source.** Computed properties are fine for derived state.
4. **Actions are async methods** named as verbs: `send()`, `fetchInbox()`, `archive(messageId:)`.
5. **Error state is a published property**, not thrown to the view.

## View Conventions

```swift
struct ComposeView: View {
    @State private var viewModel: ComposeViewModel

    init(emailService: EmailServiceProtocol) {
        _viewModel = State(initialValue: ComposeViewModel(emailService: emailService))
    }

    var body: some View {
        Form {
            TextField("To", text: $viewModel.to)
            TextField("Subject", text: $viewModel.subject)
            // ... body editor
        }
        .toolbar {
            Button("Send") { Task { await viewModel.send() } }
                .disabled(viewModel.isSending)
        }
        .alert(item: $viewModel.error) { error in
            Alert(title: Text("Error"), message: Text(error.localizedDescription))
        }
    }
}
```

### Rules for Views

1. **Views are thin** — layout and binding only, no business logic.
2. **Use `Task { }` to bridge** sync SwiftUI callbacks to async ViewModel methods.
3. **Prefer `@State` for owned ViewModels**, `@Environment` for shared app-level state.
4. **Extract reusable subviews** when a `body` exceeds ~40 lines.

## AppKit ↔ SwiftUI Bridging

For features requiring AppKit (e.g., NSToolbar, NSSplitView, menu bar):

```swift
struct AppKitToolbarWrapper: NSViewControllerRepresentable {
    func makeNSViewController(context: Context) -> ToolbarHostController {
        ToolbarHostController()
    }
    func updateNSViewController(_ controller: ToolbarHostController, context: Context) {}
}
```

### WKWebView Bridging (Email Composer)

The compose editor uses WKWebView with `contenteditable`. Communication flows through:

- **Swift → JS**: `webView.evaluateJavaScript(_:)` for getting content, formatting commands
- **JS → Swift**: `WKScriptMessageHandler` for content changes, link clicks, image paste events

Always use the `WKScriptMessageHandler` path for JS→Swift. Do NOT poll with evaluateJavaScript.

## Navigation

Use `NavigationSplitView` for the three-column email layout:

```
Sidebar (accounts/folders) | List (message list) | Detail (message content)
```

Selection state lives in a shared `@Observable NavigationState` object injected via `@Environment`.

## File Organization

```
Sources/UnleashedMail/
├── Views/
│   ├── Compose/
│   ├── Inbox/
│   ├── MessageDetail/
│   └── Sidebar/
├── ViewModels/
│   ├── ComposeViewModel.swift
│   ├── InboxViewModel.swift
│   └── ...
├── Services/
│   ├── Protocols/
│   └── Implementations/
├── Models/
├── Database/
└── Utilities/
```
