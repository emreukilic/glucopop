# Changelog

## 0.2.1 – 2026-09-19
- Fix: a sensor still warming up is reported by Medtrum as a glucose of 0, not as no reading. Zero is below every low threshold, so GlucoPop showed 0 on the widget and classified it as an urgent low — a hypo alert, repeating on the fast five-minute schedule, for a sensor that had not started yet. Readings outside a plausible range (and readings with an implausible timestamp) are now treated as no reading at all, on every source. Found on a real sensor change.
- Fix: an urgent low no longer stops being urgent the moment it goes stale. Staleness used to be decided before the glucose thresholds, so a dangerous low that was a minute past the stale limit lost its urgency and dropped to the slow repeat. It now keeps priority until twice the stale threshold, after which the staleness alert — the right one for a sensor that has actually stopped — takes over.
- Internal: a helper that guessed mmol/L vs mg/dL from the size of the number no longer does. A genuine severe hypo in mg/dL is small enough to be mistaken for mmol/L and multiplied by 18.
- Internal: the alert logic moved out of `core` into `alerts`, so it no longer sits behind a Qt import. `core` had described itself as Qt-agnostic logic for a while; the part of this app where a mistake is dangerous was the part no test could reach. It has 15 tests now.

## 0.1.4 – 2026-09-16
- Corporate networks: use the Windows certificate store (truststore) so TLS-inspection proxies no longer cause SSL errors; clearer SSL error message.

## 0.1.3 – 2026-09-15
- Fix: tray menu showed only "Hide widget" (menu actions were garbage-collected). All items are back.
- Medtrum EasyView verified with a real account.

## 0.1.2 – 2026-09-15
- Installer now terminates a running GlucoPop and overwrites it (in-place upgrade), installs per-user (no admin).
- In-app update check (every 6 h) with one-click silent install from GitHub Releases.
- "Sign out (forget account)" tray action.

## 0.1.1 – 2026-09-15
- First public release (installer + portable exe).
- Medtrum: browser-like request headers, longer timeout.
- Offline adapter tests run in CI.

## 0.1.0 – 2026-09-15
- First release: Dexcom Share, LibreLinkUp, Medtrum EasyView (patient + EasyFollow), Nightscout / xDrip+ web service.
- Setup wizard (TR/EN), always-on-top widget, tray icon with live value, notifications (low / urgent low / high / stale), autostart.
