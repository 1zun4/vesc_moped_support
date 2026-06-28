import Vedder.vesc.vescinterface 1.0;import "qrc:/mobile";import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.3

Item {
    anchors.fill: parent

    ScrollView {
        anchors.fill: parent
        anchors.margins: 10
        contentWidth: availableWidth

        ColumnLayout {
            width: parent.width
            spacing: 14

            Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: "This package uses a fixed TCA9535 pin mapping. " +
                      "Pin numbers follow the TCA9535 scheme (P0x = 0-7, P1x = 10-17)."
            }

            GroupBox {
                Layout.fillWidth: true
                title: "Pin Mapping"

                GridLayout {
                    anchors.fill: parent
                    columns: 3
                    rowSpacing: 6
                    columnSpacing: 12

                    // Header row
                    Label { text: "Signal"; font.bold: true }
                    Label { text: "Pin #"; font.bold: true }
                    Label { text: "Polarity"; font.bold: true }

                    Label { text: "Mode Button Left" }
                    Label { text: "2" }
                    Label { text: "Active-low" }

                    Label { text: "Mode Button Right" }
                    Label { text: "3" }
                    Label { text: "Active-low" }

                    Label { text: "Brake Switch" }
                    Label { text: "6" }
                    Label { text: "Active-high" }

                    Label { text: "Sidestand" }
                    Label { text: "7" }
                    Label { text: "Active-low" }

                    Label { text: "Cruise Button" }
                    Label { text: "12" }
                    Label { text: "Active-low" }

                    Label { text: "Start Button" }
                    Label { text: "10" }
                    Label { text: "Active-low" }

                    Label { text: "Ignition Input" }
                    Label { text: "13" }
                    Label { text: "Active-high" }
                }
            }
        }
    }
}
