# pad2osc

Gamepad to VRChat OSC bridge for Windows

pad2osc は、ゲームパッド入力を VRChat の OSC Input に変換して送信する Windows 用ツールです。  
VRChat のウィンドウが非アクティブ時にもゲームパッドから VRChat を操作できます。

トレイ常駐型で動作し、設定GUIから詳細な調整が可能です。



## 機能

- Gamepad → VRChat OSC 入力変換
- VRChat が非アクティブのときのみ送信
- トレイ常駐
- GUIによる設定
- config.json 自動リロード
- Voice Toggle / Push-to-Talk 対応
- Grab トリガー対応
- デッドゾーン・感度・カーブ調整
- 単一 exe で動作



## システム要件

- Windows 11
- VRChat (OSC enabled)
- XInput 対応ゲームパッド
    - Frydigi Direwolf で動作確認しています



## インストール

1. Releases から exe をダウンロード

```

pad2osc.exe

```

2. 任意のフォルダに配置

3. 実行

トレイにアイコンが表示されます。



## 設定

トレイアイコン右クリック → 「設定」

設定内容：

- VRChat IP / Port
- スティック感度
- デッドゾーン
- ボタン割り当て
- OSCアドレス
- Voice mode (pulse / hold)

設定は

```

config.json

```

に保存されます。

実行中でも自動反映されます。



## VRChat OSC設定

VRChat で OSC を有効にします：

```

Launch Options:

--enable-osc

```

または

```

OSC Enabled: On

```

## Windowsがゲームパッド入力に反応する場合

Windowsはゲームパッド入力をスタートメニューなどで使用します。

これを防ぐには HidHide の使用を推奨します：

https://github.com/ViGEm/HidHide

## ライセンス

MIT License



## ソースコード

GitHub:
https://github.com/kaguya-chan/pad2osc



## 使用ライブラリ
- python-osc
- pystray
- pillow



## 免責事項
- このツールはVRChat社とは関係ありません。
- このソフトウェアは「現状のまま」提供されます。
- このソフトウェアの使用または使用不能により生じたいかなる損害（データ損失、システム障害、その他の損害を含む）についても、作者(kaguyachan)は一切の責任を負いません。
- 本ソフトウェアの使用は自己責任で行ってください。

