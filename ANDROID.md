# Split Expense — Android app

Native **Android** client for the same backend as the web app (`/api/v1`). It covers **register / login**, **organizations** (create, list, invite by mobile), **events** (create, list), **event members**, **pool contributions**, **expenses** (equal split among selected members or custom per-member amounts), **balances**, and **Excel export** (`.xlsx`).

## Prerequisites

- **Android Studio** Ladybug (2024.2+) or newer, with **Android SDK 35** and **JDK 17** (bundled JDK is fine).
- The **FastAPI** server running and reachable from the device or emulator (see below).

## Open the project

1. In Android Studio: **File → Open** and select the `android` folder inside this repository (the folder that contains `settings.gradle.kts`).
2. Wait for **Gradle sync**. If Gradle asks to download the wrapper or SDK components, accept.
3. If the Gradle wrapper is missing, use **File → Settings → Build, Execution, Deployment → Gradle** and run sync again, or from a machine with Gradle installed run in `android/`:

   `gradle wrapper --gradle-version 8.9`

   then reopen the project.

## API base URL (important)

The app talks to the backend at **`BuildConfig.API_BASE_URL`**, which must include the **`/api/v1/`** prefix.

| Where you run the app | Typical base URL (no trailing slash in Gradle property) |
|----------------------|----------------------------------------------------------|
| **Android Emulator** (backend on same PC) | `http://10.0.2.2:8000/api/v1` |
| **Physical device** (USB / same Wi‑Fi) | `http://<YOUR_PC_LAN_IP>:8000/api/v1` (not `127.0.0.1`) |

Default in `app/build.gradle.kts` is the emulator URL above.

### Override without editing source

From the `android` directory, pass a Gradle property (PowerShell example):

```powershell
cd android
.\gradlew assembleDebug "-PAPI_BASE_URL=http://192.168.1.50:8000/api/v1"
```

Or add to `android/gradle.properties` (do not commit secrets; this is only for your machine):

```properties
API_BASE_URL=http://192.168.1.50:8000/api/v1
```

The build appends a single `/` so Retrofit paths like `auth/login` resolve correctly.

### HTTP vs HTTPS

Debug builds allow **cleartext HTTP** (`usesCleartextTraffic` + network security config) so local development works. For production, serve the API over **HTTPS** and tighten the network security config.

## Host the backend (“server”)

From the **repository root** (parent of `android/`), not inside `android/`:

```powershell
cd c:\python35\Open\expense_tracker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- **`0.0.0.0`** makes the API reachable from the emulator (`10.0.2.2`) and from other devices on your LAN.
- Web UI: `http://127.0.0.1:8000` on the PC; API docs: `http://127.0.0.1:8000/docs`.

Firewall: allow inbound **TCP 8000** on the PC if a physical phone cannot connect.

## Run the Android app

1. Start **uvicorn** as above.
2. In Android Studio, select a device (**Pixel API 34** emulator or a physical device with USB debugging).
3. Click **Run** (green triangle) on the `app` configuration.

First launch: **Register** or **Sign in** with the same mobile/password rules as the server (10–15 digit mobile, password min length 6).

## Build a release APK (optional)

```powershell
cd android
.\gradlew assembleRelease
```

Output: `app/build/outputs/apk/release/`. You must configure signing for a store-ready APK (Android Studio **Build → Generate Signed Bundle / APK**).

## Manual test checklist (parity with web)

Use a test user (or two phones / emulator + web) to verify:

1. **Register** → sign out → **Login**.
2. **Organizations**: create org; list shows it; open org.
3. **Org invite**: invite a second user’s **mobile** (user must exist); second user should see the org after login.
4. **Events**: create event; open event from list.
5. **Members**: add members (with/without optional mobile).
6. **Pool**: add contributions for different members; list updates.
7. **Expenses**: add expense with **equal split** (checkboxes); amounts should match total. Uncheck **Equal split** and enter **custom amounts** per member that sum to the total.
8. **Balances**: contributed / expended / remaining look consistent after pool + expenses.
9. **Export**: toolbar download icon saves `.xlsx` under app external files and opens a chooser (Sheets / Excel / file manager).

## Troubleshooting

| Symptom | What to check |
|--------|----------------|
| `Connection refused` / timeout | Server `--host 0.0.0.0`, correct **API_BASE_URL**, firewall, phone on same Wi‑Fi as PC. |
| `401` on every call | Sign out and sign in again; token stored in DataStore. |
| Excel opens empty / wrong file | Try another viewer app; file is under the app’s external files directory. |
| `Cleartext not permitted` | Only on strict builds; debug manifest allows cleartext for dev. |

## Project layout (high level)

- `app/src/main/java/com/splitt/expense/` — `MainActivity`, `SplitExpenseApp`, `SessionStore` (JWT in DataStore), Retrofit `ApiService`.
- `app/src/main/java/com/splitt/expense/ui/screens/` — Compose UI: auth, orgs, org detail, event tabs.
