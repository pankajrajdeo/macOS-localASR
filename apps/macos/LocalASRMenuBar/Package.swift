// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "LocalASRMenuBar",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "LocalASRMenuBar", targets: ["LocalASRMenuBar"])
    ],
    targets: [
        .executableTarget(name: "LocalASRMenuBar")
    ]
)

