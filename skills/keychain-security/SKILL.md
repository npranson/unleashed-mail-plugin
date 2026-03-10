---
name: keychain-security
description: >
  Keychain and credential management patterns for UnleashedMail. Activates when
  working with OAuth tokens, stored credentials, encryption keys, or any
  Security.framework / Keychain Services code.
allowed-tools: Read, Write, Edit, Grep, Glob
---

# Keychain Security — UnleashedMail

## Architecture Decision

UnleashedMail uses a **single encryption key** stored in Keychain to encrypt all
sensitive data at rest, rather than storing each credential as a separate Keychain item.

```
Keychain
  └── com.unleashedservices.unleashedmail.master-key (256-bit AES key)
        ↓ encrypts
      Encrypted credential store (SQLite via GRDB or file)
        ├── Gmail OAuth access token
        ├── Gmail OAuth refresh token
        └── User preferences (if sensitive)
```

### Why Single Key

- Fewer Keychain access prompts during development (separate dev keychain mitigates build-time signing prompts)
- Atomic credential operations — no partial state if one Keychain write fails
- Easier to rotate — re-encrypt the store with a new key

## Keychain Access Wrapper

```swift
import Security

enum KeychainError: Error {
    case itemNotFound
    case duplicateItem
    case unexpectedStatus(OSStatus)
    case dataConversionFailed
}

struct KeychainService {
    private let service = "com.unleashedservices.unleashedmail"

    func store(key: String, data: Data) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]

        let status = SecItemAdd(query as CFDictionary, nil)
        if status == errSecDuplicateItem {
            let updateQuery: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: key
            ]
            let updateAttrs: [String: Any] = [kSecValueData as String: data]
            let updateStatus = SecItemUpdate(updateQuery as CFDictionary, updateAttrs as CFDictionary)
            guard updateStatus == errSecSuccess else {
                throw KeychainError.unexpectedStatus(updateStatus)
            }
        } else if status != errSecSuccess {
            throw KeychainError.unexpectedStatus(status)
        }
    }

    func retrieve(key: String) throws -> Data {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else {
            if status == errSecItemNotFound { throw KeychainError.itemNotFound }
            throw KeychainError.unexpectedStatus(status)
        }
        return data
    }

    func delete(key: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unexpectedStatus(status)
        }
    }
}
```

## Dev Keychain Setup

To avoid Xcode build-time Keychain prompts in development:

1. Create a separate dev keychain:
   ```bash
   security create-keychain -p "" ~/Library/Keychains/UnleashedMail-Dev.keychain-db
   security set-keychain-settings ~/Library/Keychains/UnleashedMail-Dev.keychain-db
   ```
2. In Xcode scheme → Run → Arguments → Environment Variables, set:
   ```
   UNLEASHED_KEYCHAIN_NAME=UnleashedMail-Dev
   ```
3. Conditionally use this keychain in debug builds only.

## Entitlements

Required in `UnleashedMail.entitlements`:

```xml
<key>keychain-access-groups</key>
<array>
    <string>$(AppIdentifierPrefix)com.unleashedservices.unleashedmail</string>
</array>
```

## Security Rules

1. **Never log token values** — log token metadata (expiry, scope) only.
2. **Use `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`** — tokens should not sync via iCloud Keychain.
3. **Wipe tokens on sign-out** — delete all Keychain items for the account.
4. **Token refresh should be atomic** — if refresh fails, do not partially update stored tokens.
5. **Never store tokens in UserDefaults, plist files, or unencrypted GRDB columns.**
