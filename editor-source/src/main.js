
import { basicSetup } from "codemirror";
import { EditorView } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { autocompletion } from "@codemirror/autocomplete";
import { oneDark } from "@codemirror/theme-one-dark";

import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { json } from "@codemirror/lang-json";

import "./editor.css";

let view = null;

function getLanguage(fileName) {
    const ext = (fileName || "")
        .split(".")
        .pop()
        .toLowerCase();

    switch (ext) {
        case "py": return python();
        case "js": return javascript();
        case "html": return html();
        case "css": return css();
        case "json": return json();
        default: return [];
    }
}

window.createTatalooEditor = function(code, fileName) {
    const parent = document.getElementById("editor");

    if (view) view.destroy();

    view = new EditorView({
        state: EditorState.create({
            doc: code || "",
            extensions: [
                basicSetup,
                oneDark,
                autocompletion(),
                getLanguage(fileName),
                EditorView.lineWrapping,

                EditorView.updateListener.of(update => {
                    if (
                        update.docChanged &&
                        window.TatalooBridge
                    ) {
                        window.TatalooBridge.onCodeChanged(
                            update.state.doc.toString()
                        );
                    }
                })
            ]
        }),
        parent
    });
};

window.setEditorCode = function(code) {
    if (!view) return;

    const oldCode = view.state.doc.toString();

    if (oldCode === code) return;

    view.dispatch({
        changes: {
            from: 0,
            to: oldCode.length,
            insert: code || ""
        }
    });
};

window.getEditorCode = function() {
    return view ? view.state.doc.toString() : "";
};

function initializeEditor() {
    window.createTatalooEditor(
        "print('Welcome to Tataloo Code')",
        "main.py"
    );
}

if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        initializeEditor,
        { once: true }
    );
} else {
    initializeEditor();
}
