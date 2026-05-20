"""Mercury MVP GUI scaffold.

Run with:
    python3 mercury_gui.py
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk


@dataclass(frozen=True)
class Article:
    title: str
    source: str
    published: str
    url: str
    summary: str
    content: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    unread_count: int


SAMPLE_FEEDS = [
    Feed("Hacker News", "https://news.ycombinator.com/rss", 12),
    Feed("OpenAI Blog", "https://openai.com/blog/rss.xml", 4),
    Feed("Python Insider", "https://blog.python.org/feeds/posts/default", 7),
]


SAMPLE_ARTICLES = [
    Article(
        title="Building local-first AI reading tools",
        source="Hacker News",
        published="2026-05-20",
        url="https://example.com/local-first-ai-reader",
        summary="A short discussion about designing AI-enhanced readers that keep user data local.",
        content=(
            "Mercury is a local-first RSS reader concept. The core workflow is simple: "
            "subscribe to feeds, fetch articles, clean noisy webpages, then use AI agents "
            "for summary, translation, tagging, and export.\n\n"
            "The important engineering choice is to keep the GUI, feed service, content "
            "cleaner, AI agents, model providers, and local storage separated behind clear "
            "interfaces. That allows the team to build modules in parallel."
        ),
        tags=("local-first", "ai", "rss"),
    ),
    Article(
        title="Why content cleanup matters for RSS readers",
        source="OpenAI Blog",
        published="2026-05-19",
        url="https://example.com/content-cleanup",
        summary="Cleaned HTML and Markdown make downstream summarization and translation more stable.",
        content=(
            "RSS feeds often contain partial content, tracking links, broken markup, or "
            "layout fragments. A dedicated ContentCleaner module should normalize article "
            "text before the AI layer sees it.\n\n"
            "For the first MVP, this screen uses sample content. Later, the ContentCleaner "
            "owner can replace this placeholder with Readability-style extraction."
        ),
        tags=("readability", "markdown"),
    ),
    Article(
        title="Designing model-neutral LLM providers",
        source="Python Insider",
        published="2026-05-18",
        url="https://example.com/model-neutral-provider",
        summary="A provider interface lets Mercury support OpenAI-compatible APIs and local models.",
        content=(
            "The LLMProvider interface should hide vendor-specific request formats from "
            "agents. SummaryAgent, TranslationAgent, and TagAgent should call one stable "
            "method and receive structured results.\n\n"
            "UsageTracker can record calls, latency, token estimates, and cost estimates "
            "without exposing private article content outside the local app."
        ),
        tags=("llm", "provider", "privacy"),
    ),
]


class MercuryApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Mercury")
        self.geometry("1180x760")
        self.minsize(960, 620)

        self.feeds = SAMPLE_FEEDS
        self.articles = SAMPLE_ARTICLES
        self.selected_article = self.articles[0]

        self._configure_theme()
        self._build_layout()
        self._populate_feeds()
        self._populate_articles()
        self._show_article(self.selected_article)

    def _configure_theme(self) -> None:
        self.configure(bg="#f6f7f9")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Root.TFrame", background="#f6f7f9")
        style.configure("Panel.TFrame", background="#ffffff", relief="flat")
        style.configure("Toolbar.TFrame", background="#20242c")
        style.configure("Title.TLabel", background="#20242c", foreground="#ffffff", font=("Arial", 18, "bold"))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#69707d", font=("Arial", 11))
        style.configure("Section.TLabel", background="#ffffff", foreground="#20242c", font=("Arial", 13, "bold"))
        style.configure("Primary.TButton", font=("Arial", 11, "bold"), padding=(12, 8))
        style.configure("Tool.TButton", font=("Arial", 10), padding=(10, 7))

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(18, 12))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="Mercury", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        search = ttk.Entry(toolbar, textvariable=self.search_var)
        search.grid(row=0, column=1, sticky="ew", padx=18)
        search.insert(0, "Search articles...")
        ttk.Button(toolbar, text="Add Feed", style="Primary.TButton", command=self._add_feed).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(toolbar, text="Refresh", style="Primary.TButton", command=self._refresh).grid(row=0, column=3)

        main = ttk.Frame(self, style="Root.TFrame", padding=14)
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, minsize=230, weight=0)
        main.columnconfigure(1, minsize=300, weight=1)
        main.columnconfigure(2, minsize=430, weight=2)
        main.rowconfigure(0, weight=1)

        self.feed_list = tk.Listbox(main, borderwidth=0, highlightthickness=0, font=("Arial", 12), activestyle="none")
        self.feed_list.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.feed_list.bind("<<ListboxSelect>>", self._on_feed_select)

        article_panel = ttk.Frame(main, style="Panel.TFrame", padding=12)
        article_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 12))
        article_panel.rowconfigure(1, weight=1)
        article_panel.columnconfigure(0, weight=1)
        ttk.Label(article_panel, text="Articles", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.article_list = tk.Listbox(article_panel, borderwidth=0, highlightthickness=0, font=("Arial", 12), activestyle="none")
        self.article_list.grid(row=1, column=0, sticky="nsew")
        self.article_list.bind("<<ListboxSelect>>", self._on_article_select)

        reader = ttk.Frame(main, style="Panel.TFrame", padding=14)
        reader.grid(row=0, column=2, sticky="nsew")
        reader.columnconfigure(0, weight=1)
        reader.rowconfigure(3, weight=1)

        self.article_title = ttk.Label(reader, text="", style="Section.TLabel", wraplength=560)
        self.article_title.grid(row=0, column=0, sticky="ew")
        self.article_meta = ttk.Label(reader, text="", style="Muted.TLabel")
        self.article_meta.grid(row=1, column=0, sticky="ew", pady=(4, 12))

        actions = ttk.Frame(reader, style="Panel.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        for index, (label, command) in enumerate(
            [
                ("Clean", self._clean_article),
                ("Summary", self._summarize),
                ("Translate", self._translate),
                ("Tags", self._tag_article),
                ("Export", self._export_article),
            ]
        ):
            ttk.Button(actions, text=label, style="Tool.TButton", command=command).grid(row=0, column=index, padx=(0, 8))

        text_frame = ttk.Frame(reader, style="Panel.TFrame")
        text_frame.grid(row=3, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.article_text = tk.Text(
            text_frame,
            wrap="word",
            borderwidth=0,
            padx=8,
            pady=8,
            font=("Arial", 13),
            bg="#ffffff",
            fg="#20242c",
            insertbackground="#20242c",
        )
        self.article_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.article_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.article_text.configure(yscrollcommand=scrollbar.set)

        self.status = ttk.Label(self, text="Ready. MVP scaffold uses sample data.", anchor="w", padding=(14, 8))
        self.status.grid(row=2, column=0, sticky="ew")

    def _populate_feeds(self) -> None:
        self.feed_list.delete(0, tk.END)
        self.feed_list.insert(tk.END, "All feeds")
        for feed in self.feeds:
            self.feed_list.insert(tk.END, f"{feed.name}  ({feed.unread_count})")
        self.feed_list.selection_set(0)

    def _populate_articles(self, source: str | None = None) -> None:
        self.article_list.delete(0, tk.END)
        visible_articles = [a for a in self.articles if source is None or a.source == source]
        for article in visible_articles:
            self.article_list.insert(tk.END, article.title)
        self.visible_articles = visible_articles
        if visible_articles:
            self.article_list.selection_set(0)
            self._show_article(visible_articles[0])

    def _show_article(self, article: Article) -> None:
        self.selected_article = article
        self.article_title.configure(text=article.title)
        self.article_meta.configure(text=f"{article.source} | {article.published} | {article.url}")
        self.article_text.configure(state="normal")
        self.article_text.delete("1.0", tk.END)
        self.article_text.insert(tk.END, article.content)
        self.article_text.configure(state="disabled")
        self.status.configure(text=f"Selected: {article.title}")

    def _on_feed_select(self, _event: tk.Event) -> None:
        selection = self.feed_list.curselection()
        if not selection:
            return
        index = selection[0]
        source = None if index == 0 else self.feeds[index - 1].name
        self._populate_articles(source)

    def _on_article_select(self, _event: tk.Event) -> None:
        selection = self.article_list.curselection()
        if selection:
            self._show_article(self.visible_articles[selection[0]])

    def _add_feed(self) -> None:
        messagebox.showinfo("Add Feed", "MVP placeholder: connect this button to FeedService.add_feed(url).")

    def _refresh(self) -> None:
        self.status.configure(text="Refresh placeholder: FeedService.refresh_all() will be connected here.")

    def _clean_article(self) -> None:
        self.status.configure(text="Clean placeholder: ContentCleaner will produce cleaned HTML and Markdown.")

    def _summarize(self) -> None:
        messagebox.showinfo("Summary", self.selected_article.summary)
        self.status.configure(text="Summary generated from sample data.")

    def _translate(self) -> None:
        messagebox.showinfo("Translation", "翻译占位：这里之后接入 TranslationAgent。")
        self.status.configure(text="Translation placeholder executed.")

    def _tag_article(self) -> None:
        tags = ", ".join(self.selected_article.tags)
        messagebox.showinfo("Tags", tags)
        self.status.configure(text=f"Tags: {tags}")

    def _export_article(self) -> None:
        self.status.configure(text="Export placeholder: Markdown / HTML exporter will be connected here.")


def main() -> None:
    app = MercuryApp()
    app.mainloop()


if __name__ == "__main__":
    main()
