plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

fun buildVersionCode(version: String): Int {
    val parts = version.split(".")
    require(parts.size == 3 && parts.all { it.toIntOrNull() != null }) {
        "relayviewVersion must be major.minor.patch, got $version"
    }
    val (major, minor, patch) = parts.map(String::toInt)
    require(major in 0..1999 && minor in 0..999 && patch in 0..999)
    return major * 1_000_000 + minor * 1_000 + patch
}

val relayVersion = providers.gradleProperty("relayviewVersion").orElse("0.5.1").get()
val releaseRepo = providers.gradleProperty("relayviewRepo").orElse("").get()
require(releaseRepo.isEmpty() || Regex("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+").matches(releaseRepo))
val signingPath = System.getenv("RELAYVIEW_KEYSTORE")
val canSign = !signingPath.isNullOrBlank() && !System.getenv("RELAYVIEW_KEYSTORE_PASSWORD").isNullOrBlank() &&
    !System.getenv("RELAYVIEW_KEY_ALIAS").isNullOrBlank() && !System.getenv("RELAYVIEW_KEY_PASSWORD").isNullOrBlank()

android {
    namespace = "com.relayview.android"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.relayview.android"
        minSdk = 26
        targetSdk = 35
        versionCode = buildVersionCode(relayVersion)
        versionName = relayVersion
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "UPDATE_REPO", "\"$releaseRepo\"")
    }

    if (canSign) {
        signingConfigs {
            create("relayRelease") {
                storeFile = file(signingPath!!)
                storePassword = System.getenv("RELAYVIEW_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("RELAYVIEW_KEY_ALIAS")
                keyPassword = System.getenv("RELAYVIEW_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        getByName("debug") {
            // Debug builds intentionally use the machine's default Android debug certificate.
        }
        getByName("release") {
            isMinifyEnabled = false
            if (canSign) signingConfig = signingConfigs.getByName("relayRelease")
        }
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.08.01")
    implementation(composeBom)
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.9.2")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.2")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.media3:media3-exoplayer:1.10.1")
    implementation("androidx.media3:media3-exoplayer-rtsp:1.10.1")
    implementation("androidx.media3:media3-exoplayer-hls:1.10.1")
    implementation("androidx.media3:media3-ui:1.10.1")
    testImplementation("junit:junit:4.13.2")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
