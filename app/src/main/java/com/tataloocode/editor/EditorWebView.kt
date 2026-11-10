
package com.tataloocode.editor

import android.annotation.SuppressLint
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import org.json.JSONObject

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun EditorWebView(
    code: String,
    onCodeChanged: (String) -> Unit,
    command: String,
    commandId: Int,
    modifier: Modifier = Modifier
) {
    var webView by remember { mutableStateOf<WebView?>(null) }
    var pageLoaded by remember { mutableStateOf(false) }

    AndroidView(
        modifier = modifier,
        factory = { context ->
            WebView(context).apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true

                webChromeClient = WebChromeClient()

                webViewClient = object : WebViewClient() {
                    override fun onPageFinished(
                        view: WebView,
                        url: String
                    ) {
                        pageLoaded = true
                        view.evaluateJavascript(
                            "window.setEditorCode(${JSONObject.quote(code)})",
                            null
                        )
                    }
                }

                addJavascriptInterface(
                    EditorBridge(onCodeChanged),
                    "TatalooBridge"
                )

                loadUrl("file:///android_asset/editor/index.html")
                webView = this
            }
        }
    )

    LaunchedEffect(code, pageLoaded) {
        if (pageLoaded) {
            webView?.evaluateJavascript(
                "window.setEditorCode(${JSONObject.quote(code)})",
                null
            )
        }
    }

    LaunchedEffect(commandId) {
        if (pageLoaded && command.isNotBlank()) {
            webView?.evaluateJavascript(
                "window.tatalooCommand(${JSONObject.quote(command)})",
                null
            )
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            webView?.destroy()
            webView = null
        }
    }
}
