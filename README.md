# AAZ LegacyChat for iOS 16

LegacyChat is an experimental, sandboxed browser build for accessing ChatGPT and modern web content on legacy iOS devices. It is based on a pinned Reynard Browser revision and applies a small, reviewable compatibility and security overlay.

## Download and installation

1. Download `LegacyChat-iOS16.ipa` from the latest GitHub Release.
2. Install it with TrollStore or TrollStore Lite.
3. Open LegacyChat and sign in through the official `chatgpt.com` website if required.

Tested on iOS `16.7.16` and iPadOS `16.6`. Compatibility with other versions is not guaranteed.

## Included changes

- Opens `chatgpt.com` on the initial tab and new tabs.
- Adds reliable public UIKit file-picker presentation on iOS 16.
- Backports text, HTML, and image clipboard support used by the pinned browser revision.
- Uses the independent bundle identifier `com.aaz.legacychat`.
- Builds the normal sandboxed application without TrollStore or jailbreak JIT helpers.
- Hard-disables JIT, the external update feed, and third-party add-on installation.
- Removes background modes, file sharing, and unnecessary camera, microphone, photo-library, and location declarations.

Photo selection is handled by the system picker. Image paste uses the local iOS pasteboard.

## Privacy and security

This overlay adds no analytics, advertising, telemetry service, or custom account server. Website traffic and sign-in are handled by the sites you visit and remain subject to their privacy policies. LegacyChat is not the official ChatGPT application.

The hardening script refuses to modify any upstream revision except the pinned commit. Review `scripts/harden.py` and `patches/nsClipboard.mm.patch` for the complete overlay.

## Source and reproducibility

The distributed application consists of:

- Reynard Browser revision `a7e06a6484422d474afce3ff4f496be076a8a90f` (`0.10.1`).
- The deterministic overlay in this repository.

To prepare matching source:

```sh
git clone https://github.com/minh-ton/reynard-browser.git upstream
git -C upstream checkout a7e06a6484422d474afce3ff4f496be076a8a90f
git -C upstream submodule update --init --recursive
python3 scripts/harden.py upstream
```

Build the resulting upstream tree using Reynard's documented iOS build process. Apple platform tooling and the upstream build dependencies are required.

## License and attribution

Reynard Browser is by Minh Ton and contributors and is licensed under GPL-3.0. Mozilla-derived components and patches retain their applicable licenses, including MPL-2.0. See `LICENSE`, `NOTICE.md`, and the upstream source for details.

This independent experimental project is not affiliated with or endorsed by Reynard, Mozilla, Apple, or OpenAI.
