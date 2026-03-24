# Accessibility Patterns — UnleashedMail

## Overview

UnleashedMail is fully accessible with VoiceOver, keyboard navigation, Dynamic Type,
and color contrast compliance. All UI components follow macOS accessibility guidelines.
Accessibility is mandatory — no feature ships without full a11y support.

## Core Principles

1. **No accessibility without functionality** — Every interactive element must be fully usable by assistive technologies
2. **Keyboard-first design** — All actions available via keyboard shortcuts
3. **Dynamic Type support** — Text scales with system settings
4. **Color independence** — No color-only state indicators
5. **Clear focus management** — Logical tab order, visible focus rings

## SwiftUI Accessibility Modifiers

### Basic Labels and Hints

```swift
Button("Send", systemImage: "paperplane") {
    // action
}
.accessibilityLabel("Send email")
.accessibilityHint("Sends the composed email to recipients")
```

### Custom Controls

```swift
// Custom gesture-based control
Rectangle()
    .fill(Color.blue)
    .frame(width: 50, height: 50)
    .onTapGesture {
        toggleStar()
    }
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(isStarred ? "Remove star" : "Add star")
    .accessibilityHint("Toggles star status for this message")
    .accessibilityAddTraits(.isButton)
    .accessibilityValue(isStarred ? "Starred" : "Not starred")
```

### Complex Components

```swift
List(messages, selection: $selectedMessage) { message in
    MessageRow(message: message)
}
.accessibilityLabel("Message list")
.accessibilityHint("Select a message to view its contents")
```

### Message Row

```swift
struct MessageRow: View {
    let message: MailMessage

    var body: some View {
        HStack {
            Circle()
                .fill(message.isRead ? Color.clear : Color.blue)
                .frame(width: 8, height: 8)
                .accessibilityHidden(true)  // Decorative

            VStack(alignment: .leading) {
                Text(message.sender)
                    .font(.headline)
                Text(message.subject)
                    .font(.subheadline)
                    .lineLimit(1)
                Text(message.snippet)
                    .font(.caption)
                    .lineLimit(1)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityHint("Double tap to open message")
        .accessibilityAddTraits(message.isRead ? [] : .isSelected)
    }

    private var accessibilityLabel: String {
        let readStatus = message.isRead ? "" : "Unread, "
        return "\(readStatus)From \(message.sender), \(message.subject)"
    }
}
```

## Focus Management

### Keyboard Navigation

```swift
@AccessibilityFocusState private var focusedField: Field?

enum Field {
    case to, subject, body
}

TextField("To", text: $to)
    .accessibilityFocused($focusedField, equals: .to)

TextField("Subject", text: $subject)
    .accessibilityFocused($focusedField, equals: .subject)

TextEditor(text: $body)
    .accessibilityFocused($focusedField, equals: .body)
```

### Rotor Support

```swift
// Custom rotor for navigation
.accessibilityRotor("Unread Messages") {
    ForEach(unreadMessages) { message in
        AccessibilityRotorEntry(message.subject, id: message.id)
    }
}
```

## Dynamic Type

### Scalable Text

```swift
Text("Welcome to UnleashedMail")
    .font(.largeTitle)  // Scales with Dynamic Type

// Custom font that scales
Text("Message")
    .font(.system(size: 16, weight: .medium, design: .default))  // ❌ Doesn't scale

Text("Message")
    .font(.body)  // ✅ Scales automatically
```

### Layout Adaptation

```swift
VStack {
    Text("Subject")
        .font(.headline)
    Text(subject)
        .font(.body)
        .lineLimit(nil)  // Allow wrapping
        .fixedSize(horizontal: false, vertical: true)  // Grow vertically
}
```

## Color and Contrast

### Semantic Colors

```swift
// ✅ Adapts to light/dark mode and high contrast
Color.primary
Color.secondary
Color.accentColor

// ❌ Hardcoded colors
Color.blue
Color.white
```

### State Indicators

```swift
// ✅ Multiple indicators
HStack {
    Image(systemName: message.isStarred ? "star.fill" : "star")
    Text(message.subject)
}
.foregroundColor(message.isStarred ? .yellow : .gray)

// ❌ Color only
Text(message.subject)
    .foregroundColor(message.isStarred ? .yellow : .primary)
```

## VoiceOver Announcements

### Live Updates

```swift
// Announce when content changes
.onChange(of: messageCount) { oldValue, newValue in
    let announcement = "\(newValue) messages"
    AccessibilityNotification.Announcement(announcement).post()
}
```

### Custom Announcements

```swift
func sendEmail() async {
    // Send logic...
    AccessibilityNotification.Announcement("Email sent successfully").post()
}
```

## Testing Accessibility

### Xcode Accessibility Inspector

```bash
# Launch Accessibility Inspector
open /Applications/Xcode.app/Contents/Developer/Applications/Accessibility\ Inspector.app
```

### UI Tests

```swift
func testMessageRow_accessibility() throws {
    let app = XCUIApplication()
    app.launch()

    let messageRow = app.descendants(matching: .any)["Message from John Doe"]
    XCTAssertTrue(messageRow.exists)
    XCTAssertEqual(messageRow.label, "From John Doe, Welcome to the team")
    XCTAssertEqual(messageRow.value as? String, "Unread")
}
```

### Manual Testing Checklist

- [ ] VoiceOver can navigate all elements
- [ ] Tab key moves focus logically
- [ ] All buttons have labels and hints
- [ ] Dynamic Type scales text appropriately
- [ ] High Contrast mode works
- [ ] Reduced Motion respects preferences
- [ ] Keyboard shortcuts work without mouse

## Common Patterns

### Form Fields

```swift
TextField("Email Address", text: $email)
    .accessibilityLabel("Recipient email address")
    .accessibilityHint("Enter the email address of the recipient")
    .textContentType(.emailAddress)
    .keyboardType(.emailAddress)
```

### Progress Indicators

```swift
ProgressView("Sending email...", value: progress)
    .accessibilityLabel("Sending email progress")
    .accessibilityValue("\(Int(progress * 100)) percent complete")
```

### Modal Dialogs

```swift
.sheet(isPresented: $showCompose) {
    ComposeView()
        .accessibilityAddTraits(.isModal)
}
```

## Dual Implementation Accessibility

Since UnleashedMail has dual implementations (native + WebKit compose, simple + full email detail), both must be equally accessible:

### Compose Editor

```swift
// Native SwiftUI editor
TextEditor(text: $body)
    .accessibilityLabel("Email body")
    .accessibilityHint("Compose the content of your email")

// WebKit editor
WebView(html: composeHTML)
    .accessibilityLabel("Email composition editor")
    .accessibilityHint("Use rich text editing to compose your email")
```

### Email Detail

```swift
// Simple WebView
WebView(html: messageHTML)
    .accessibilityLabel("Email content")
    .accessibilityHint("Read the full content of the email")

// Full WebView (with additional features)
WebView(html: enhancedHTML)
    .accessibilityLabel("Email content with attachments")
    .accessibilityHint("Read the email and access attachments")
```

## Compliance Standards

- **WCAG 2.1 AA**: 4.5:1 contrast ratio for normal text, 3:1 for large text
- **Section 508**: US government accessibility requirements
- **EN 301 549**: European accessibility standard

All features must pass these standards before release.