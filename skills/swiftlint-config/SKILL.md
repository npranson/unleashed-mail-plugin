# SwiftLint Configuration and Code Style Enforcement — UnleashedMail

## Overview

UnleashedMail enforces code style with SwiftLint. Configuration in `.swiftlint.yml`
is strict but pragmatic. All rules are enabled with appropriate warnings/errors.
Functions ≤50 lines (error), files ≤600 lines (error).

## SwiftLint Configuration

```yaml
# .swiftlint.yml
included:
  - Sources
  - Tests

excluded:
  - .build
  - DerivedData
  - Packages

# Line length — relaxed for readability
line_length:
  warning: 120
  error: 150
  ignores_comments: true

# Function body length
function_body_length:
  warning: 40
  error: 50

# File length
file_length:
  warning: 400
  error: 600
  ignore_comment_only_lines: true

# Type body length
type_body_length:
  warning: 300
  error: 500

# Cyclomatic complexity
cyclomatic_complexity:
  warning: 10
  error: 15

# Force unwrap
force_unwrapping: error

# Force try
force_try: error

# Force cast
force_cast: error

# Unused code
unused_declaration: warning
unused_import: warning

# Naming conventions
type_name:
  min_length: 3
  max_length: 40
identifier_name:
  min_length: 2
  max_length: 40
  allowed_symbols: ["_"]

# Access control
private_over_fileprivate: warning

# Trailing whitespace
trailing_whitespace: warning

# Colon spacing
colon: warning

# Semicolon
semicolon: warning

# Opening brace
opening_brace: warning

# Custom rules for UnleashedMail
custom_rules:
  no_print_statements:
    name: "No print statements"
    regex: "print\\("
    message: "Use Logger instead of print"
    severity: error

  no_nslog:
    name: "No NSLog"
    regex: "NSLog\\("
    message: "Use Logger instead of NSLog"
    severity: error

  no_try_question_mark:
    name: "No try?"
    regex: "try\\?"
    message: "Use do-catch instead of try? to handle errors properly"
    severity: error

  no_force_cast_as:
    name: "No force cast as!"
    regex: "as!"
    message: "Avoid force casting — use optional casting or proper error handling"
    severity: error

  pii_logging_check:
    name: "PII in logging"
    regex: "Logger.*\\$\\{.*email\\|Logger.*\\$\\{.*subject\\|Logger.*\\$\\{.*body"
    message: "Potential PII in log statement — use PIIRedactor"
    severity: warning
```

## Installation and Usage

### Install SwiftLint

```bash
# Via Homebrew
brew install swiftlint

# Via Mint (recommended for CI)
mint install realm/SwiftLint
```

### Run SwiftLint

```bash
# Check current directory
swiftlint

# Auto-fix what can be fixed
swiftlint --fix

# Check specific file
swiftlint Sources/ViewModels/InboxViewModel.swift

# Generate report
swiftlint --reporter html > swiftlint-report.html
```

### CI Integration

```yaml
# .github/workflows/ci.yml
- name: Run SwiftLint
  run: |
    brew install swiftlint
    swiftlint --strict --reporter github-actions-logging
```

## Code Style Guidelines

### Naming

```swift
// ✅ Good
struct MailMessage: Identifiable {
    let id: String
    let subject: String
    let sender: String
}

// ❌ Bad — too short
struct MM {
    let i: String
    let s: String
    let sr: String
}
```

### Access Control

```swift
// ✅ Good — explicit internal
internal final class InboxViewModel {
    internal var messages: [MailMessage] = []
    private let emailService: EmailServiceProtocol
}

// ❌ Bad — implicit internal
final class InboxViewModel {
    var messages: [MailMessage] = []
    let emailService: EmailServiceProtocol
}
```

### Function Length

```swift
// ✅ Good — short and focused
func sendEmail() async throws {
    let draft = composeDraft()
    try await validateDraft(draft)
    try await emailService.send(draft)
    updateUI()
}

// ❌ Bad — too long
func sendEmail() async throws {
    let draft = composeDraft()
    try await validateDraft(draft)
    try await emailService.send(draft)
    updateUI()
    // 50+ more lines...
}
```

### Error Handling

```swift
// ✅ Good — explicit error handling
do {
    try await sendEmail()
} catch {
    Logger.debug("Failed to send email: \(error)", category: .ui)
}

// ❌ Bad — silent failure
try? sendEmail()
```

### Logging

```swift
// ✅ Good — structured logging
Logger.debug("Sending email to \(PIIRedactor.redactEmail(recipient))", category: .network)

// ❌ Bad — print statements
print("Sending email to \(recipient)")
```

## Custom Rules Implementation

Add custom rules to `.swiftlint.yml`:

```yaml
custom_rules:
  no_direct_urlsession:
    name: "No direct URLSession"
    regex: "URLSession\\."
    message: "Use HTTPBasedAIProvider or service protocols instead of direct URLSession"
    severity: error

  actor_isolation_check:
    name: "Actor isolation"
    regex: "class.*ViewModel.*ObservableObject"
    message: "ViewModels should be actors or use @Observable — not ObservableObject"
    severity: warning
```

## IDE Integration

### Xcode

1. Install SwiftLint via Homebrew
2. Add build phase script:

```bash
if which swiftlint >/dev/null; then
    swiftlint --fix
    swiftlint
else
    echo "warning: SwiftLint not installed"
fi
```

### VS Code

Add to `.vscode/tasks.json`:

```json
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "SwiftLint",
            "type": "shell",
            "command": "swiftlint",
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "silent",
                "focus": false,
                "panel": "shared"
            }
        }
    ]
}
```

## Common Violations and Fixes

### Line Length

```swift
// ❌ Too long
let longVariableName = someVeryLongFunctionCall(withManyParameters: param1, andAnother: param2, andYetAnother: param3)

// ✅ Break into multiple lines
let longVariableName = someVeryLongFunctionCall(
    withManyParameters: param1,
    andAnother: param2,
    andYetAnother: param3
)
```

### Cyclomatic Complexity

```swift
// ❌ Too complex
func processMessage(_ message: MailMessage) {
    if message.isRead {
        if message.hasAttachments {
            if message.isStarred {
                // Complex nested logic
            }
        }
    }
}

// ✅ Extract methods
func processMessage(_ message: MailMessage) {
    guard !message.isRead else { return }
    processUnreadMessage(message)
}

private func processUnreadMessage(_ message: MailMessage) {
    if message.hasAttachments {
        processAttachmentMessage(message)
    }
}
```

## Enforcement

- **CI**: SwiftLint runs on every PR, failures block merge
- **Pre-commit**: SwiftLint auto-fix runs before commits
- **Manual**: Developers run `swiftlint` locally

Violations are tracked in Jira tickets with "swiftlint" label.