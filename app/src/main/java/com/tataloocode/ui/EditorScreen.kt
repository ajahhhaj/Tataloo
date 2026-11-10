
package com.tataloocode.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.tataloocode.editor.EditorTab
import com.tataloocode.editor.EditorWebView

@Composable
fun EditorScreen() {
    var tabs by remember {
        mutableStateOf(
            listOf(
                EditorTab(
                    1,
                    "main.py",
                    "print('Hello Tataloo Code')"
                )
            )
        )
    }

    var selectedId by remember { mutableIntStateOf(1) }
    var nextId by remember { mutableIntStateOf(2) }
    var terminalVisible by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Ready") }

    val selected = tabs.find { it.id == selectedId }
    val currentName = selected?.name ?: "Untitled"

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF090909))
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                "TATALOO CODE",
                color = Color.White,
                style = MaterialTheme.typography.headlineSmall
            )

            Text(
                "NATIVE ANDROID IDE",
                color = Color(0xFFB51232),
                style = MaterialTheme.typography.labelSmall
            )
        }

        EditorToolbar(
            fileName = currentName,
            onNew = {
                val tab = EditorTab(
                    nextId,
                    "untitled${nextId}.py"
                )
                tabs = tabs + tab
                selectedId = nextId
                nextId++
                status = "New file created"
            },
            onSave = {
                status = "Save integration pending"
            },
            onRun = {
                status = "Runtime integration pending"
            },
            onTerminal = {
                terminalVisible = !terminalVisible
            }
        )

        Row(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
        ) {
            FileExplorer(
                files = tabs.map { it.name },
                selectedFile = currentName,
                onFileSelected = { name ->
                    selectedId = tabs.first { it.name == name }.id
                }
            )

            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(Color(0xFF191919))
                ) {
                    tabs.forEach { tab ->
                        TextButton(
                            onClick = { selectedId = tab.id }
                        ) {
                            Text(
                                tab.name,
                                color = if (tab.id == selectedId)
                                    Color(0xFFE04460)
                                else Color.LightGray
                            )
                        }
                    }
                }

                EditorWebView(
                    code = selected?.content ?: "",
                    onCodeChanged = { newCode ->
                        tabs = tabs.map {
                            if (it.id == selectedId)
                                it.copy(
                                    content = newCode,
                                    modified = true
                                )
                            else it
                        }
                    },
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                )

                if (terminalVisible) {
                    Surface(
                        color = Color(0xFF171717),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(120.dp)
                    ) {
                        Text(
                            "TATALOO TERMINAL\n$status",
                            color = Color(0xFFE04460),
                            modifier = Modifier.padding(12.dp)
                        )
                    }
                }
            }
        }

        Text(
            text = status,
            color = Color.LightGray,
            modifier = Modifier
                .fillMaxWidth()
                .background(Color(0xFF151515))
                .padding(8.dp)
        )
    }
}
