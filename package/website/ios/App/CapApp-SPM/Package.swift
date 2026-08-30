// swift-tools-version: 5.9
import PackageDescription

// DO NOT MODIFY THIS FILE - managed by Capacitor CLI commands
let package = Package(
    name: "CapApp-SPM",
    platforms: [.iOS(.v15)],
    products: [
        .library(
            name: "CapApp-SPM",
            targets: ["CapApp-SPM"])
    ],
    dependencies: [
        .package(url: "https://github.com/ionic-team/capacitor-swift-pm.git", exact: "8.5.0"),
        .package(name: "CapacitorApp", path: "..\..\..\node_modules\.pnpm\@capacitor+app@8.1.1_@capacitor+core@8.5.0\node_modules\@capacitor\app"),
        .package(name: "CapacitorBarcodeScanner", path: "..\..\..\node_modules\.pnpm\@capacitor+barcode-scanner@3.1.1_@capacitor+core@8.5.0\node_modules\@capacitor\barcode-scanner"),
        .package(name: "CapacitorPreferences", path: "..\..\..\node_modules\.pnpm\@capacitor+preferences@8.0.1_@capacitor+core@8.5.0\node_modules\@capacitor\preferences"),
        .package(name: "DevioartsCapacitorMdns", path: "..\..\..\node_modules\.pnpm\@devioarts+capacitor-mdns@0.1.0_@capacitor+core@8.5.0\node_modules\@devioarts\capacitor-mdns")
    ],
    targets: [
        .target(
            name: "CapApp-SPM",
            dependencies: [
                .product(name: "Capacitor", package: "capacitor-swift-pm"),
                .product(name: "Cordova", package: "capacitor-swift-pm"),
                .product(name: "CapacitorApp", package: "CapacitorApp"),
                .product(name: "CapacitorBarcodeScanner", package: "CapacitorBarcodeScanner"),
                .product(name: "CapacitorPreferences", package: "CapacitorPreferences"),
                .product(name: "DevioartsCapacitorMdns", package: "DevioartsCapacitorMdns")
            ]
        )
    ]
)
