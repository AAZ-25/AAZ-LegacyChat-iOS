#!/usr/bin/env python3
"""Apply deterministic security hardening to pinned Reynard 0.10.1 source."""

from __future__ import annotations

import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

PINNED_COMMIT = "a7e06a6484422d474afce3ff4f496be076a8a90f"
CHAT_URL = "https://chatgpt.com/"
BUNDLE_ID = "com.aaz.legacychat"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: harden.py UPSTREAM_DIRECTORY")

    root = Path(sys.argv[1]).resolve()
    actual = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != PINNED_COMMIT:
        raise SystemExit(f"refusing unpinned upstream commit: {actual}")

    # Backport the upstream image-clipboard implementation added immediately
    # after Reynard 0.10.1. Keep the upstream patch byte-for-byte reviewable.
    overlay_patch = Path(__file__).resolve().parent.parent / "patches/nsClipboard.mm.patch"
    clipboard_patch = root / "patches/widget/uikit/nsClipboard.mm.patch"
    shutil.copyfile(overlay_patch, clipboard_patch)

    # The normal app keeps only the memory entitlement needed by Gecko.
    main_entitlements = {
        "com.apple.developer.kernel.increased-memory-limit": True,
    }
    helper_entitlements: dict[str, object] = {}
    for relative, payload in (
        ("browser/Reynard/Entitlements/Reynard.entitlements", main_entitlements),
        ("browser/Helper/Entitlements/Reynard-Helper.entitlements", helper_entitlements),
    ):
        with (root / relative).open("wb") as stream:
            plistlib.dump(payload, stream, fmt=plistlib.FMT_XML, sort_keys=True)

    # JIT is permanently off in this build and no background JIT service starts.
    app_delegate = root / "browser/Reynard/AppDelegate.swift"
    replace_once(
        app_delegate,
        "        JITController.shared.startBackgroundAudioIfNeeded()\n",
        "",
    )

    prefs = root / "browser/Reynard/Client/Preferences/BrowserPreferences.swift"
    prefs_text = prefs.read_text()
    jit_pattern = re.compile(
        r"    struct JITSettings \{.*?^    \}\n    \n    // MARK: - Experimental",
        re.MULTILINE | re.DOTALL,
    )
    jit_replacement = """    struct JITSettings {
        static var hasPairingFile: Bool { false }

        static var isJITEnabled: Bool {
            get { false }
            set { _ = newValue }
        }
    }
    
    // MARK: - Experimental"""
    prefs_text, count = jit_pattern.subn(jit_replacement, prefs_text, count=1)
    if count != 1:
        raise SystemExit("failed to hard-disable JIT preferences")
    prefs.write_text(prefs_text)
    replace_once(
        prefs,
        'key("NewTabSettings", "newTabDisplayOption"): NewTabDisplayOption.homepage.rawValue,',
        'key("NewTabSettings", "newTabDisplayOption"): NewTabDisplayOption.customURL.rawValue,',
    )
    replace_once(
        prefs,
        'key("NewTabSettings", "customNewTabURL"): "",',
        f'key("NewTabSettings", "customNewTabURL"): "{CHAT_URL}",',
    )
    replace_once(
        prefs,
        'key("HomepageSettings", "showsNewUpdates"): true,',
        'key("HomepageSettings", "showsNewUpdates"): false,',
    )

    # Firefox 153 needs bootstrapping on current macOS/Xcode runners. This is
    # the minimal upstream build-script fix added after Reynard 0.10.1.
    gecko_builder = root / "tools/development/build-gecko.sh"
    replace_once(
        gecko_builder,
        '\techo "ac_add_options --disable-tests"\n',
        '\techo "ac_add_options --disable-tests"\n'
        '\techo "ac_add_options --enable-bootstrap"\n',
    )

    # Reynard 0.10.1 predates its --no-signing implementation. Force an
    # unsigned archive so GitHub never needs an Apple certificate or profile.
    app_builder = root / "tools/release/build-app.sh"
    replace_once(
        app_builder,
        'xcodebuild archive -scheme "Reynard" -archivePath "$DIST_DIR/Reynard.xcarchive" -project "$PROJECT_PATH" -sdk iphoneos -arch arm64 -configuration Release -xcconfig "$DIST_DIR/Reynard.xcconfig"\n',
        'xcodebuild archive -scheme "Reynard" -archivePath "$DIST_DIR/Reynard.xcarchive" -project "$PROJECT_PATH" -sdk iphoneos -arch arm64 -configuration Release -xcconfig "$DIST_DIR/Reynard.xcconfig" CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY="" PROVISIONING_PROFILE_SPECIFIER=""\n',
    )

    # Reynard 0.10.1's Gecko copy phase falls back to an unavailable
    # Apple Development identity even when the archive is intentionally unsigned.
    # Use the minimal later-upstream fix: ad-hoc sign embedded Gecko code whenever
    # Xcode disables signing or provides no identity.
    gecko_copier = root / "browser/Scripts/AddGecko.sh"
    replace_once(
        gecko_copier,
        'SIGN_IDENTITY="${EXPANDED_CODE_SIGN_IDENTITY:-${EXPANDED_CODE_SIGN_IDENTITY_NAME:-Apple Development}}"\n'
        'DEFAULT_THEME_SRC=',
        'SIGN_IDENTITY="${EXPANDED_CODE_SIGN_IDENTITY:-}"\n'
        'if [ "${CODE_SIGNING_ALLOWED:-YES}" = "NO" ] || [ -z "${SIGN_IDENTITY}" ]; then\n'
        '\tSIGN_IDENTITY=-\n'
        'fi\n\n'
        'DEFAULT_THEME_SRC=',
    )

    # Open ChatGPT on first launch as well as every new tab.
    browser = root / "browser/Reynard/Client/Interface/BrowserViewController.swift"
    replace_once(
        browser,
        "        tabManager.createInitialTab(openingScreen: Prefs.HomepageSettings.openingScreen)\n"
        "        refreshAddressBar()",
        "        tabManager.createInitialTab(openingScreen: Prefs.HomepageSettings.openingScreen)\n"
        "        applyNewTabDisplayOption(toTabAt: tabManager.selectedTabIndex)\n"
        "        refreshAddressBar()",
    )

    # Use a public UIKit action sheet for file selection. The private anchored
    # menu handoff in 0.10.1 can silently fail on legacy iOS/TrollStore.
    file_picker_menu = root / (
        "browser/Reynard/Client/Interface/ContentView/WebContent/"
        "FilePicker/FilePickerMenu.swift"
    )
    replace_once(
        file_picker_menu,
        """        guard #available(iOS 14.0, *), !anchorRect.isEmpty else {
            showActionSheet(in: geckoView)
            return
        }
        
        let button = FilePickerMenuAnchorButton(frame: anchorRect)
        button.backgroundColor = .clear
        button.menu = buildMenu()
        button.showsMenuAsPrimaryAction = true
        button.onMenuDismissed = { [weak self] in
            self?.handleMenuDismissed()
        }
        
        geckoView.addSubview(button)
        anchorButton = button
        presentMenuFromAnchorButton()
""",
        """        // Public UIKit presentation reliably hands off to
        // PHPicker/UIDocumentPicker on iOS 16.
        showActionSheet(in: geckoView)
""",
    )

    # Disable the external update feed completely.
    updates = root / "browser/Reynard/Client/Startup/BrowserUpdates.swift"
    replace_once(
        updates,
        'private static let sourceURL = "https://github.com/minh-ton/reynard-browser/releases/download/0.0.1-a1/source.json"',
        'private static let sourceURL = ""',
    )

    # Prevent installation of third-party Firefox extensions.
    addon_commands = root / "browser/GeckoView/Addons/AddonRuntimeCommands.swift"
    addon_text = addon_commands.read_text()
    pattern = re.compile(
        r"    func install\(url: String, installMethod: AddonInstallMethod\? = nil\) async throws -> Addon \{.*?^    \}\n",
        re.MULTILINE | re.DOTALL,
    )
    replacement = (
        "    func install(url: String, installMethod: AddonInstallMethod? = nil) "
        "async throws -> Addon {\n"
        '        throw GeckoHandlerError("Add-ons are disabled in LegacyChat")\n'
        "    }\n"
    )
    addon_text, count = pattern.subn(replacement, addon_text, count=1)
    if count != 1:
        raise SystemExit("failed to disable add-on installation")
    addon_commands.write_text(addon_text)

    # Remove URL hijacking, background modes, file sharing, add-on document types,
    # and device permissions that ChatGPT text chat does not need.
    info_path = root / "browser/Reynard/Resources/Info.plist"
    with info_path.open("rb") as stream:
        info = plistlib.load(stream)
    info["CFBundleURLTypes"] = [
        {
            "CFBundleURLName": BUNDLE_ID,
            "CFBundleURLSchemes": ["legacychat"],
        }
    ]
    for key in (
        "UIBackgroundModes",
        "UIFileSharingEnabled",
        "UTImportedTypeDeclarations",
        "NSCameraUsageDescription",
        "NSMicrophoneUsageDescription",
        "NSPhotoLibraryUsageDescription",
        "NSPhotoLibraryAddUsageDescription",
        "NSLocationWhenInUseUsageDescription",
    ):
        info.pop(key, None)
    with info_path.open("wb") as stream:
        plistlib.dump(info, stream, fmt=plistlib.FMT_XML, sort_keys=True)

    # Use independent identifiers so this build cannot replace official Reynard.
    package_script = root / "tools/release/create-ipa.sh"
    replacements = {
        "com.minh-ton.Reynard.Helper": f"{BUNDLE_ID}.Helper",
        "com.minh-ton.Reynard.OpenIn": f"{BUNDLE_ID}.OpenIn",
        "com.minh-ton.Reynard": BUNDLE_ID,
    }
    package_text = package_script.read_text()
    for old, new in replacements.items():
        if old not in package_text:
            raise SystemExit(f"missing bundle identifier in packaging script: {old}")
        package_text = package_text.replace(old, new)
    package_script.write_text(package_text)

    print("LegacyChat hardening applied to pinned Reynard 0.10.1 source")


if __name__ == "__main__":
    main()
