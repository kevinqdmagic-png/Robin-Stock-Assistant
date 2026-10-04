plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "com.robin.stock"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.robin.stock"
        minSdk = 26
        targetSdk = 35
        versionCode = 13
        versionName = "0.7.4"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    val releaseStorePath = providers.environmentVariable("ROBIN_UPLOAD_KEYSTORE").orNull
    val releaseStorePassword = providers.environmentVariable("ROBIN_UPLOAD_STORE_PASSWORD").orNull
    val releaseKeyAlias = "robin-upload"
    val releaseKeyPassword = releaseStorePassword
    val hasSecureReleaseSigning = listOf(
        releaseStorePath,
        releaseStorePassword,
    ).all { !it.isNullOrBlank() }
    signingConfigs {
        if (hasSecureReleaseSigning) {
            create("secureRelease") {
                storeFile = file(releaseStorePath!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }
    buildTypes {
        getByName("release") {
            if (hasSecureReleaseSigning) {
                signingConfig = signingConfigs.getByName("secureRelease")
            }
        }
    }
}
dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    testImplementation("junit:junit:4.13.2")
}
