
package com.tataloocode.editor

import android.annotation.SuppressLint
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun EditorWebView(
    code: String,
    onCodeChanged: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var webView by remember { mutableStateOf<WebView?>(null) }

    AndroidView(
        modifier = modifier,
        factory = { context ->
            WebView(context).apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.allowFileAccess = true
                webViewClient = WebViewClient()

                addJavascriptInterface(
                    EditorBridge(onCodeChanged),
                    "TatalooBridge"
                )

                loadUrl("file:///android_asset/editor/index.html")
                webView = this
            }
        },
        update = {
            if (it !== webView) webView = it
        }
    )

    LaunchedEffect(code, webView) {
        webView?.evaluateJavascript(
            "setEditorCode(${org.json.JSONObject.quote(code)})",
            null
        )
    }
}
