
package com.tataloocode.ui

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Crimson = Color(0xFFB51232)
private val Background = Color(0xFF090909)
private val SurfaceDark = Color(0xFF151515)

@Composable
fun EditorTheme(content: @Composable () -> Unit) {
    val scheme = darkColorScheme(
        primary = Crimson,
        background = Background,
        surface = SurfaceDark,
        secondary = Color(0xFF8D1830),
        onBackground = Color.White,
        onSurface = Color.White
    )

    MaterialTheme(
        colorScheme = scheme,
        content = content
    )
}
