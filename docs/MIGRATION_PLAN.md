Tataloo Code — Native Android Migration

Project Identity

- Project: Tataloo Code
- Creator: aMiR Tataloo
- Package: com.tataloocode
- Platform: Android
- Language: Kotlin
- UI: Jetpack Compose
- Architecture: Modular, maintainable, testable

Migration Strategy

The existing Python implementation is the functional reference.
The target application must be independently implemented using native Android technologies.

Do not blindly translate Python syntax into Kotlin.
Analyze existing behavior, identify dependencies, and redesign each feature for Android.

Core Technology Decisions

- Kotlin
- Jetpack Compose
- AndroidX
- Room for structured local data
- DataStore for preferences
- Android Storage Access Framework for file access
- WebView with CodeMirror 6 for the code editor
- Gradle Kotlin DSL
- GitHub Actions for APK builds

Development Milestones

M0 — Repository Preparation

- [ ] Inspect existing repository
- [ ] Establish native Android project structure
- [ ] Configure Gradle
- [ ] Configure Android manifest
- [ ] Configure GitHub Actions

M1 — Native Foundation

- [ ] MainActivity
- [ ] Compose application entry point
- [ ] Navigation
- [ ] Dark theme
- [ ] Basic application settings
- [ ] Debug APK build

M2 — File Management

- [ ] File explorer
- [ ] Open and save files
- [ ] Create, rename, move and delete
- [ ] Workspace management

M3 — Code Editor

- [ ] CodeMirror integration
- [ ] Syntax highlighting
- [ ] Tabs
- [ ] Search and replace
- [ ] Editor preferences
- [ ] Autosave and recovery

M4 — Advanced Interface

- [ ] Command palette
- [ ] Quick tools
- [ ] Split editor
- [ ] Context menus
- [ ] Theme engine

M5 — Developer Tools

- [ ] Language services
- [ ] Diagnostics
- [ ] Formatting
- [ ] Terminal
- [ ] Runtime adapters

M6 — Advanced Features

- [ ] HTML preview
- [ ] Git integration
- [ ] Backup and restore
- [ ] Remote access
- [ ] Plugin architecture

M7 — Quality and Release

- [ ] Unit tests
- [ ] UI tests
- [ ] Performance testing
- [ ] Security review
- [ ] Release APK

Engineering Rules

1. No fake or nonfunctional features.
2. No placeholder implementations presented as completed functionality.
3. No destructive changes to the existing Python implementation.
4. Keep modules focused and maintainable.
5. Test each milestone before proceeding.
6. Document platform and runtime limitations.
7. Preserve the intended Tataloo Code visual identity.
8. Do not copy proprietary Acode source code or assets.

Design Identity

- Default theme: Tataloo Midnight
- Primary colors: black, charcoal and deep crimson
- Minimal, professional and mobile-first interface
- Persian and English interface support
- Default interface language: Persian

Current Status

Migration preparation started.
Python reference implementation is pending.
Native implementation has not yet been declared complete.
