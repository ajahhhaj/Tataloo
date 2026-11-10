
package com.tataloocode.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.tataloocode.editor.EditorTab
import com.tataloocode.editor.EditorWebView

@Composable
fun EditorScreen() {
    val context = LocalContext.current

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

    var command by remember { mutableStateOf("") }
    var commandId by remember { mutableIntStateOf(0) }

    val selected = tabs.find { it.id == selectedId }
    val currentName = selected?.name ?: "Untitled"

    fun updateStatus(message: String) {
        status = message
    }

    val openLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) {
            runCatching {
                val content = context.contentResolver
                    .openInputStream(uri)
                    ?.bufferedReader()
                    ?.use { it.readText() }
                    ?: ""

                val name = uri.lastPathSegment
                    ?.substringAfterLast('/')
                    ?.substringAfterLast(':')
                    ?.takeIf { it.isNotBlank() }
                    ?: "opened_file.txt"

                val tab = EditorTab(
                    nextId,
                    name,
                    content
                )

                tabs = tabs + tab
                selectedId = nextId
                nextId++

                updateStatus("File opened")
            }.onFailure {
                updateStatus("Could not open file: ${it.message}")
            }
        }
    }

    val saveLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("text/plain")
    ) { uri: Uri? ->
        if (uri != null) {
            runCatching {
                val content = tabs
                    .find { it.id == selectedId }
                    ?.content ?: ""

                context.contentResolver
                    .openOutputStream(uri, "wt")
                    ?.bufferedWriter()
                    ?.use { it.write(content) }
                    ?: error("Unable to write file")

                tabs = tabs.map {
                    if (it.id == selectedId)
                        it.copy(modified = false)
                    else it
                }

                updateStatus("File saved successfully")
            }.onFailure {
                updateStatus("Save failed: ${it.message}")
            }
        }
    }

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
                color = Color(0xFFE04460),
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

                updateStatus("New file created")
            },
            onOpen = {
                openLauncher.launch(arrayOf("*/*"))
            },
            onSave = {
                val name = currentName
                    .substringAfterLast('/')
                    .ifBlank { "untitled.txt" }

                saveLauncher.launch(name)
            },
            onUndo = {
                command = "undo"
                commandId++
            },
            onRedo = {
                command = "redo"
                commandId++
            },
            onSearch = {
                command = "search"
                commandId++
            },
            onRun = {
                updateStatus(
                    "Python runtime is not installed yet"
                )
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
                    selectedId = tabs.first {
                        it.name == name
                    }.id
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
                            onClick = {
                                selectedId = tab.id
                            }
                        ) {
                            Text(
                                text = tab.name +
                                    if (tab.modified) " •" else "",
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
                            if (it.id == selectedId) {
                                it.copy(
                                    content = newCode,
                                    modified = true
                                )
                            } else it
                        }
                    },
                    command = command,
                    commandId = commandId,
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
