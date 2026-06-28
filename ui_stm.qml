import Vedder.vesc.vescinterface 1.0;import "qrc:/mobile";import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.3
import Vedder.vesc.commands 1.0
import Vedder.vesc.utility 1.0

Item {
    id: root
    anchors.fill: parent

    property Commands mCommands: VescIf.commands()
    property bool alarmArmed: false

    Component.onCompleted: {
        sendCode("(send-settings)")
    }

    function sendCode(str) {
        mCommands.sendCustomAppData(str + "\0")
    }

    function boolColor(val) {
        return val ? "#4CAF50" : "#9E9E9E"
    }

    ScrollView {
        anchors.fill: parent
        anchors.margins: 10
        contentWidth: availableWidth

        ColumnLayout {
            width: parent.width
            spacing: 14

            // ── Live Status ──────────────────────────────────────────────
            GroupBox {
                Layout.fillWidth: true
                title: "Live Status"

                GridLayout {
                    anchors.fill: parent
                    columns: 3
                    rowSpacing: 8
                    columnSpacing: 12

                    // Active
                    Rectangle {
                        id: indActive
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Active (scooter on)" }
                    Item { Layout.fillWidth: true }

                    Rectangle {
                        id: indIgnition
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Ignition On" }
                    Item { Layout.fillWidth: true }

                    // Start button
                    Rectangle {
                        id: indStart
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Start Button" }
                    Item { Layout.fillWidth: true }

                    // Mode left
                    Rectangle {
                        id: indModeLeft
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Mode Button Left" }
                    Item { Layout.fillWidth: true }

                    // Mode right
                    Rectangle {
                        id: indModeRight
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Mode Button Right" }
                    Item { Layout.fillWidth: true }

                    // Brake
                    Rectangle {
                        id: indBrake
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Brake Switch" }
                    Item { Layout.fillWidth: true }

                    // Sidestand
                    Rectangle {
                        id: indSide
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Sidestand Down" }
                    Item { Layout.fillWidth: true }

                    // Cruise
                    Rectangle {
                        id: indCruise
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Cruise Button" }
                    Item { Layout.fillWidth: true }

                    Rectangle {
                        id: indCruiseActive
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Cruise Active" }
                    Item { Layout.fillWidth: true }

                    Rectangle {
                        id: indElectronics
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Electronics On" }
                    Item { Layout.fillWidth: true }

                    Rectangle {
                        id: indAlarm
                        width: 18; height: 18; radius: 9
                        color: boolColor(false)
                    }
                    Label { text: "Alarm Armed" }
                    Item { Layout.fillWidth: true }
                }
            }

            Button {
                Layout.fillWidth: true
                text: root.alarmArmed ? "Disarm Alarm" : "Arm Alarm"
                onClicked: sendCode(root.alarmArmed ? "(disarm-alarm)" : "(arm-alarm)")
            }

            // ── Settings ─────────────────────────────────────────────────
            GroupBox {
                Layout.fillWidth: true
                title: "Settings"

                GridLayout {
                    anchors.fill: parent
                    columns: 2
                    rowSpacing: 6
                    columnSpacing: 12

                    Label { text: "Max Speed (km/h)" }
                    SpinBox {
                        id: maxSpeed
                        Layout.fillWidth: true
                        from: 1; to: 200; stepSize: 1
                        value: 27
                    }

                    Label { text: "Max Power (W)" }
                    SpinBox {
                        id: maxWatt
                        Layout.fillWidth: true
                        from: 100; to: 50000; stepSize: 100
                        value: 1400
                    }

                    Label { text: "Accel Scale (0.01–1.00)" }
                    SpinBox {
                        id: accelScale
                        Layout.fillWidth: true
                        from: 1; to: 100; stepSize: 1
                        property real realValue: value / 100.0
                        textFromValue: function(v) { return (v / 100.0).toFixed(2) }
                        valueFromText: function(t) { return Math.round(parseFloat(t) * 100) }
                        value: 60
                    }

                    Label { text: "Regen Brake (%)" }
                    SpinBox {
                        id: regenBrake
                        Layout.fillWidth: true
                        from: 0; to: 100; stepSize: 5
                        property real realValue: value / 100.0
                        value: 30
                    }

                    Label { text: "Disable Ignition (always on)" }
                    CheckBox {
                        id: ignDisable
                        checked: false
                    }

                    Label { text: "Alarm Gyro Sensitivity (deg/s)" }
                    SpinBox {
                        id: alarmGyro
                        Layout.fillWidth: true
                        from: 1; to: 200; stepSize: 1
                        value: 10
                    }

                    Label { text: "Alarm Loudness (V)" }
                    SpinBox {
                        id: alarmVolt
                        Layout.fillWidth: true
                        from: 1; to: 50; stepSize: 1
                        value: 5
                    }

                    Button {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        text: "Save Settings"
                        onClicked: {
                            var cmd = "(save-settings " +
                                maxSpeed.value.toFixed(1) + " " +
                                maxWatt.value.toFixed(0) + " " +
                                accelScale.realValue.toFixed(2) + " " +
                                regenBrake.realValue.toFixed(2) + " " +
                                (ignDisable.checked ? "1" : "0") + " " +
                                alarmGyro.value.toFixed(1) + " " +
                                alarmVolt.value.toFixed(1) + ")"
                            sendCode(cmd)
                        }
                    }

                    Button {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        text: "Restore Defaults"
                        onClicked: {
                            sendCode("(restore-defaults)")
                            sendCode("(send-settings)")
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: mCommands

        function onCustomAppDataReceived(data) {
            var str = data.toString().trim()

            if (str.startsWith("settings ")) {
                var t = str.split(" ")
                maxSpeed.value     = Math.round(parseFloat(t[1]))
                maxWatt.value      = Math.round(parseFloat(t[2]))
                accelScale.value   = Math.round(parseFloat(t[3]) * 100)
                regenBrake.value   = Math.round(parseFloat(t[4]) * 100)
                ignDisable.checked = parseInt(t[5]) === 1
                alarmGyro.value    = Math.round(parseFloat(t[6]))
                alarmVolt.value    = Math.round(parseFloat(t[7]))
            } else if (str.startsWith("status ")) {
                var s = str.split(" ")
                indActive.color  = boolColor(parseInt(s[1]) === 1)
                indIgnition.color = boolColor(parseInt(s[2]) === 1)
                indStart.color   = boolColor(parseInt(s[3]) === 1)
                indModeLeft.color = boolColor(parseInt(s[4]) === 1)
                indModeRight.color = boolColor(parseInt(s[5]) === 1)
                indBrake.color   = boolColor(parseInt(s[6]) === 1)
                indSide.color    = boolColor(parseInt(s[7]) === 1)
                indCruise.color  = boolColor(parseInt(s[8]) === 1)
                indCruiseActive.color = boolColor(parseInt(s[9]) === 1)
                indElectronics.color = boolColor(parseInt(s[10]) === 1)
                root.alarmArmed = parseInt(s[11]) === 1
                indAlarm.color = boolColor(root.alarmArmed)
            } else if (str === "ok") {
                VescIf.emitStatusMessage("Settings saved.", true)
            }
        }
    }
}
