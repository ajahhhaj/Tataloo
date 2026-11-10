
package com.tataloocode

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val Background = Color(0xFF090909)
private val SurfaceDark = Color(0xFF151515)
private val Crimson = Color(0xFFB51232)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            TatalooCodeApp()
        }
    }
}

@Composable
fun TatalooCodeApp() {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Crimson,
            background = Background,
            surface = SurfaceDark
        )
    ) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = Background
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(20.dp)
            ) {
                Text(
                    text = "TATALOO CODE",
                    color = Color.White,
                    fontSize = 25.sp,
                    fontWeight = FontWeight.Bold
                )

                Text(
                    text = "Native Android IDE",
                    color = Crimson,
                    fontSize = 13.sp
                )

                Spacer(modifier = Modifier.height(32.dp))

                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .background(
                            SurfaceDark,
                            RoundedCornerShape(16.dp)
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "Your coding workspace",
                        color = Color.LightGray
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))

                Button(
                    onClick = {},
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Crimson
                    )
                ) {
                    Text("Open Project")
                }
            }
        }
    }
}
