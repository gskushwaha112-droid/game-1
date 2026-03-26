# APK Build Setup

Yeh project ab `Kivy + Buildozer` path ke liye prepare hai.

## 1. Windows par WSL install karo

PowerShell me:

```powershell
wsl --install
```

Phir system restart karo aur Ubuntu open karo.

## 2. Ubuntu/WSL me project folder kholo

```bash
cd /mnt/d/game1
```

## 3. Buildozer ke required packages install karo

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip \
python3-virtualenv autoconf libtool pkg-config zlib1g-dev \
libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev \
libssl-dev automake autopoint gettext
python3 -m pip install --user --upgrade buildozer cython
export PATH="$PATH:$HOME/.local/bin"
```

## 4. Python dependencies install karo

```bash
python3 -m pip install --user -r requirements.txt
```

## 5. APK build karo

```bash
buildozer android debug
```

Build hone ke baad APK aam tor par `bin/` folder me milti hai.

## 6. GitHub Actions se APK build

Repo ko GitHub par push karo. Is repo me workflow file pehle se add hai:

`/.github/workflows/android-apk.yml`

Uske baad:

1. GitHub repository kholo
2. `Actions` tab kholo
3. `Build Android APK` workflow run karo
4. Build complete hone par artifact download karo

## Important notes

- App metadata ab `Bottle Shooter Challenge` aur package domain `com.arcade.bottleshooter` par set hai.
- Agar aap apna brand naam use karna chahte ho to `buildozer.spec` me `title`, `package.name`, aur `package.domain` ko update kar lena.
- Release APK ke liye baad me signing setup alag se karna hoga.
- Pehla build kaafi time le sakta hai kyunki Android SDK/NDK download hota hai.
