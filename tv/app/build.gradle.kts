plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.spotless)
    alias(libs.plugins.detekt)
    alias(libs.plugins.roborazzi)
}

android {
    namespace = "ledger.porch.tv"
    compileSdk = 36

    defaultConfig {
        applicationId = "ledger.porch.tv"
        minSdk = 28
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:8000\"")
        buildConfigField("String", "HOUSE_KEY", "\"\"")
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions.jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    // Golden API bodies from the backend are the shared contract for tests.
    sourceSets.named("test") {
        resources.srcDir("../../backend/tests/golden")
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
    }

    lint {
        warningsAsErrors = true
        abortOnError = true
        disable +=
            setOf(
                // Versions pinned for AGP 8 / compileSdk 36 compatibility.
                "OldTargetApi",
                "AndroidGradlePluginVersion",
                "GradleDependency",
                "NewerVersionAvailable",
                // tv banner is a mandatory 320x180 full-bleed asset, not a launcher icon.
                "IconLauncherShape",
                // local.properties is generated per machine.
                "PropertyEscape",
            )
    }
}

spotless {
    kotlin {
        target("src/**/*.kt")
        ktlint(libs.versions.ktlint.get())
    }
    kotlinGradle {
        target("*.gradle.kts")
        ktlint(libs.versions.ktlint.get())
    }
}

detekt {
    config.setFrom(files("../detekt.yml"))
    buildUponDefaultConfig = true
    // Test files keep fixture builders with long parameter lists.
    source.setFrom(files("src/main"))
}

roborazzi {
    outputDir.set(file("src/test/screenshots"))
}

configurations.all {
    resolutionStrategy.dependencySubstitution {
        // Ktor 3.6 pulls okhttp 5.5, which requires compileSdk 37;
        // 5.4 keeps us on compileSdk 36 / AGP 8.
        substitute(module("com.squareup.okhttp3:okhttp"))
            .using(module("com.squareup.okhttp3:okhttp:5.4.0"))
        substitute(module("com.squareup.okhttp3:okhttp-android"))
            .using(module("com.squareup.okhttp3:okhttp-android:5.4.0"))
    }
}

dependencies {
    // Coil and friends request Compose 1.12 (needs AGP 9 + SDK 37);
    // the enforced BOM pins Compose back to the AGP 8 compatible set.
    implementation(enforcedPlatform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.foundation)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.tv.material)
    implementation(libs.tv.foundation)
    implementation(libs.activity.compose)
    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.json)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.datastore.preferences)
    implementation(libs.lifecycle.runtime.compose)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.coil.compose)
    implementation(libs.coil.network.okhttp)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.ui.compose)

    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.ktor.client.mock)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.robolectric)
    testImplementation(libs.roborazzi)
    testImplementation(libs.roborazzi.compose)
    testImplementation(libs.turbine)
    testImplementation(libs.coil.test)
    testImplementation(libs.compose.ui.test.junit4)
}
