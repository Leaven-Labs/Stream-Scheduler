"""The step-by-step guides that connect a destination: a YouTube channel or a Facebook Page.

Each guide explains what to click on the platform's own pages, says why each step is safe, and ends
by saving the sign-in in the system keychain (vault.py). Nothing is saved before the last step.
"""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

import facebook
import ui
import youtube
from store import new_id
from vault import VaultError


def steps(*lines):
    """Numbered instructions as one paragraph block."""
    items = "".join(f"<li style='margin-bottom:7px'>{line}</li>" for line in lines)
    return ui.rich(f"<ol style='margin-left:-18px; line-height:140%'>{items}</ol>")


def link(url, text=None):
    return f"<a href='{url}'>{text or url.split('//')[1]}</a>"


def secret_field(placeholder):
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.Password)   # dots, so it is not read over a shoulder or in a screen share
    edit.setPlaceholderText(placeholder)
    return edit


class YouTubeOptions(QWidget):
    """How broadcasts are made on a channel: who can see them, which stream key, for children or not."""

    def __init__(self, options=None, streams=None):
        super().__init__()
        options = options or {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.privacy = QComboBox()
        for key, text in (("public", "Public: everyone"), ("unlisted", "Unlisted: only with the link"),
                          ("private", "Private: only you")):
            self.privacy.addItem(text, key)
        self.privacy.setCurrentIndex(max(0, self.privacy.findData(options.get("privacy", "public"))))
        self.stream = QComboBox()
        self.stream.addItem("Choose later in YouTube Studio", "")
        if streams is None and options.get("stream_id"):
            streams = [{"id": options["stream_id"], "title": options.get("stream_title", "Saved stream key")}]
        for s in streams or []:
            self.stream.addItem(s["title"], s["id"])
        wanted = self.stream.findData(options.get("stream_id", ""))
        self.stream.setCurrentIndex(wanted if wanted > 0 else min(1, self.stream.count() - 1))
        self.kids = ui.Switch(options.get("made_for_kids", False))
        self.auto = ui.Switch(options.get("auto_start", True))
        rows = [("Who can watch", self.privacy, ""),
                ("Stream key", self.stream, "With a key chosen, your encoder (OBS, ATEM ...) keeps the same key every week."),
                ("Made for kids", self.kids, "YouTube requires an answer. Most services and events are not."),
                ("Start and stop by itself", self.auto,
                 "The broadcast goes live when your encoder starts sending, and ends when it stops.")]
        for i, (name, widget, hint) in enumerate(rows):
            grid.addWidget(ui.label(name, "strong"), i * 2, 0)
            grid.addWidget(widget, i * 2, 1, Qt.AlignLeft)
            if hint:
                grid.addWidget(ui.label(hint, "small", wrap=True), i * 2 + 1, 1)
        grid.setColumnStretch(1, 1)

    def value(self):
        return {"privacy": self.privacy.currentData(), "stream_id": self.stream.currentData(),
                "stream_title": self.stream.currentText() if self.stream.currentData() else "",
                "made_for_kids": self.kids.isChecked(), "auto_start": self.auto.isChecked(),
                "auto_stop": self.auto.isChecked()}


class Wizard(QDialog):
    """A dialog with the steps listed at the left and one step shown at the right."""

    def __init__(self, parent, title, icon):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 640)
        self.checks, self.marks = [], []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(232)
        self.side = QVBoxLayout(side)
        self.side.setContentsMargins(18, 22, 14, 18)
        self.side.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(ui.Icon(icon, 28))
        head.addWidget(ui.label(title, "big", wrap=True), 1)
        self.side.addLayout(head)
        self.side.addSpacing(8)
        row.addWidget(side)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        right.addWidget(ui.rule())
        bar = QHBoxLayout()
        bar.setContentsMargins(26, 12, 26, 14)
        self.error = ui.label("", "error", wrap=True)
        bar.addWidget(self.error, 1)
        self.back = ui.button("Back", clicked=lambda: self.go(self.stack.currentIndex() - 1))
        self.forward = ui.button("Next", "primary", self.next)
        bar.addWidget(ui.button("Cancel", clicked=self.reject))
        bar.addWidget(self.back)
        bar.addWidget(self.forward)
        right.addLayout(bar)
        row.addLayout(right, 1)

    def add_step(self, name, heading, widgets, check=None):
        """A step: its short name for the list, its heading, what it shows, and check() which returns
        a sentence when the user may not go on yet."""
        number = len(self.checks) + 1
        line = QHBoxLayout()
        line.setSpacing(10)
        num, text = QLabel(str(number)), ui.label(name, "stepname", wrap=True)
        num.setObjectName("stepnum")
        num.setAlignment(Qt.AlignCenter)
        line.addWidget(num, 0, Qt.AlignTop)
        line.addWidget(text, 1)
        self.side.addLayout(line)
        self.marks.append((num, text))
        body = QWidget()
        body.setObjectName("scrollbody")
        col = QVBoxLayout(body)
        col.setContentsMargins(28, 24, 28, 18)
        col.setSpacing(14)
        col.addWidget(ui.label(f"STEP {number}", "caps"))
        col.addWidget(ui.label(heading, "pagetitle", wrap=True))
        for w in widgets:
            col.addWidget(w)
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        self.stack.addWidget(scroll)
        self.checks.append(check)

    def ready(self):
        self.side.addStretch(1)
        self.go(0)

    def go(self, index):
        self.error.setText("")
        self.stack.setCurrentIndex(index)
        for i, (num, text) in enumerate(self.marks):
            state = "now" if i == index else "done" if i < index else ""
            num.setText("✓" if i < index else str(i + 1))
            ui.set_prop(num, "state", state)
            ui.set_prop(text, "state", state)
        self.back.setEnabled(index > 0)
        self.forward.setText("Finish" if index == len(self.checks) - 1 else "Next")

    def next(self):
        index = self.stack.currentIndex()
        problem = self.checks[index]() if self.checks[index] else ""
        if problem:
            self.error.setText(problem)
        elif index < len(self.checks) - 1:
            self.go(index + 1)
        else:
            problem = self.finish()
            if problem:
                self.error.setText(problem)
            else:
                self.accept()

    def finish(self):
        raise NotImplementedError


class YouTubeWizard(Wizard):
    def __init__(self, parent, store, vault):
        super().__init__(parent, "Connect YouTube", "youtube")
        self.store, self.vault = store, vault
        self.signin = self.tokens = self.channel = None
        self.destination = None

        self.add_step("Before you start", "Connect a YouTube channel", [
            ui.rich("Stream Scheduler creates your scheduled live streams through YouTube's official API. Google "
                    "asks every app to identify itself, so you will make a free <b>Google Cloud project</b> of "
                    "your own. It takes about ten minutes, once."),
            steps("You need a Google account that <b>owns or manages</b> the channel.",
                  f"Live streaming must be switched on for the channel. Check at {link('https://www.youtube.com/features')}"
                  ": the first time, YouTube takes up to 24 hours to enable it.",
                  "Schedule from a computer you trust: the sign-in is kept on this computer."),
            ui.callout("How this keeps your channel safe",
                       "The app never sees your Google password: you sign in on Google's own page in your "
                       "browser. This computer talks to Google directly, with no server of ours in between. The "
                       f"sign-in is stored in <b>{vault.where()}</b>, encrypted with your login, and you can "
                       f"revoke it at any time at {link('https://myaccount.google.com/permissions')}.")])

        self.add_step("Create a project", "Create a Google Cloud project", [
            steps(f"Open {link('https://console.cloud.google.com/projectcreate')} and sign in.",
                  "Give the project a name, for example <b>Stream Scheduler</b>, and click <b>Create</b>. "
                  "There is no charge and no billing account is needed.",
                  "With the new project selected, open "
                  f"{link('https://console.cloud.google.com/apis/library/youtube.googleapis.com', 'YouTube Data API v3')}"
                  " and click <b>Enable</b>."),
            ui.callout("Good to know", "The project belongs to you. It gets a free daily allowance from "
                       "YouTube that is far more than a few scheduled streams a week will use.")])

        self.add_step("Consent screen", "Set up the sign-in screen", [
            steps(f"Open {link('https://console.cloud.google.com/auth/overview', 'Google Auth Platform')} and click "
                  "<b>Get started</b>.",
                  "App name: <b>Stream Scheduler</b>. Support email: your own address.",
                  "Audience: <b>External</b>. Enter your email as the contact, agree, and <b>Create</b>.",
                  "Open <b>Audience</b> at the left and click <b>Publish app</b>, so the status reads "
                  "<b>In production</b>."),
            ui.callout("Do not skip 'Publish app'",
                       "While the status is <b>Testing</b>, Google ends every sign-in after 7 days and your "
                       "streams would stop being scheduled. Publishing does not make anything public: only someone "
                       "with your client secret (next step) and your Google login can use it. You do not need "
                       "Google's verification for your own use.", "warn", "warn")])

        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText("Client ID  (ends with .apps.googleusercontent.com)")
        self.client_secret = secret_field("Client secret")
        self.add_step("Create a client", "Create the app's key", [
            steps(f"Open {link('https://console.cloud.google.com/auth/clients', 'Clients')} and click "
                  "<b>Create client</b>.",
                  "Application type: <b>Desktop app</b>. Name: anything. Click <b>Create</b>.",
                  "Copy the <b>Client ID</b> and the <b>Client secret</b> into the boxes below."),
            self.client_id, self.client_secret,
            ui.callout("Treat the client secret like a password",
                       f"It is saved in {vault.where()}, not in a file. Do not email it or put it in a "
                       "shared document. If it ever leaks, delete the client in Google Cloud and make a new one.")],
            check=self.check_client)

        self.sign_button = ui.button("Sign in with Google", "primary", self.start_sign_in)
        self.sign_state = ui.label("", "sub", wrap=True)
        sign_row = QWidget()
        r = QHBoxLayout(sign_row)
        r.setContentsMargins(0, 0, 0, 0)
        r.addWidget(self.sign_button)
        r.addWidget(self.sign_state, 1)
        self.options_box = QVBoxLayout()
        holder = QWidget()
        holder.setLayout(self.options_box)
        self.options_box.setContentsMargins(0, 6, 0, 0)
        self.options = None
        self.add_step("Sign in", "Sign in and choose how to stream", [
            steps("Click the button: your browser opens Google's sign-in page.",
                  "Choose the account, and the channel if you have more than one.",
                  "Google says <b>\"Google hasn't verified this app\"</b>. That is expected, the app is your own "
                  "project: click <b>Advanced</b>, then <b>Go to Stream Scheduler</b>, then <b>Continue</b>."),
            sign_row, holder,
            ui.callout("What you are allowing",
                       "<b>Manage your YouTube account</b>: the one permission YouTube offers for creating "
                       "broadcasts. The app uses it only to create the streams of your schedules and to read "
                       "your channel's name and stream keys.")],
            check=lambda: "" if self.tokens else "Sign in with Google first.")
        self.ready()

    def check_client(self):
        if not self.client_id.text().strip().endswith(".apps.googleusercontent.com"):
            return "The Client ID should end with .apps.googleusercontent.com"
        if len(self.client_secret.text().strip()) < 10:
            return "Paste the Client secret."
        return self.vault.available()

    def start_sign_in(self):
        self.error.setText("")
        self.signin = signin = youtube.SignIn(self.client_id.text(), self.client_secret.text())
        try:
            url = signin.start()
        except OSError as exc:
            self.error.setText(f"Could not start the sign-in: {exc}")
            return
        self.sign_button.setEnabled(False)
        self.sign_state.setText("Waiting for you in the browser ...")
        QDesktopServices.openUrl(QUrl(url))

        def work():
            tokens = signin.wait()
            return tokens, youtube.channel(tokens["access_token"]), youtube.streams(tokens["access_token"])
        ui.run_async(work, self.signed_in)

    def signed_in(self, result, error):
        self.sign_button.setEnabled(True)
        if error:
            self.sign_state.setText("")
            self.error.setText(str(error))
            return
        self.tokens, self.channel, streams = result
        self.sign_state.setObjectName("good")
        ui.set_prop(self.sign_state, "x", 1)
        self.sign_state.setText(f"✓  Connected to “{self.channel['title']}”")
        self.sign_button.setText("Sign in again")
        ui.clear(self.options_box)
        self.options = YouTubeOptions(streams=streams)
        self.options_box.addWidget(self.options)
        self.raise_()
        self.activateWindow()

    def reject(self):
        if self.signin:
            self.signin.cancel()
        super().reject()

    def finish(self):
        dest = {"id": new_id(), "kind": "youtube", "name": self.channel["title"],
                "account_id": self.channel["id"], "client_id": self.client_id.text().strip(),
                "options": self.options.value()}
        try:
            self.vault.set(dest["id"], "client_secret", self.client_secret.text().strip())
            self.vault.set(dest["id"], "refresh_token", self.tokens["refresh_token"])
        except VaultError as exc:
            self.vault.forget(dest["id"], "youtube")
            return str(exc)
        self.store.destinations.append(dest)
        self.store.save()
        self.destination = dest
        return ""


class FacebookWizard(Wizard):
    def __init__(self, parent, store, vault):
        super().__init__(parent, "Connect a Facebook Page", "facebook")
        self.store, self.vault = store, vault
        self.found = []
        self.destination = None
        perms = ", ".join(f"<b>{p}</b>" for p in facebook.PERMISSIONS)

        self.add_step("Before you start", "Connect a Facebook Page", [
            ui.rich("Stream Scheduler creates your scheduled live videos through Meta's official Graph API. Meta "
                    "asks every app to identify itself, so you will make a free <b>Meta app</b> of your own and "
                    "create an access key for your Page. It takes about ten minutes, once."),
            steps("You need <b>full control</b> of the Page (Page settings → Page access).",
                  "The Page must be allowed to go live. Meta currently asks that it is at least 60 days old and "
                  "has at least 100 followers.",
                  f"Turn on two-factor authentication for your Facebook account if you have not: "
                  f"{link('https://www.facebook.com/security/2fac/settings')}. Meta requires it for developers."),
            ui.callout("How this keeps your Page safe",
                       "The app never sees your Facebook password. It keeps one thing: an access key for this "
                       f"one Page, stored in <b>{vault.where()}</b>, encrypted with your login. It can only do what "
                       "you allow in step 3, and you can cancel it at any time under Facebook → Settings → "
                       "Business integrations.")])

        self.add_step("Create a Meta app", "Create a Meta app", [
            steps(f"Open {link('https://developers.facebook.com/apps')} and sign in. If asked, register as a "
                  "developer (free).",
                  "Click <b>Create app</b>. Name it <b>Stream Scheduler</b>. When asked for a use case choose "
                  "<b>Other</b>, then the type <b>Business</b>.",
                  "In the app, open <b>App settings → Basic</b>. You will need the <b>App ID</b> and the "
                  "<b>App secret</b> (click <b>Show</b>) in step 4."),
            ui.callout("Meta changes these pages often",
                       "The names of buttons may differ a little from what is written here. What matters is the "
                       "result: an app of type Business whose App ID and App secret you can see.")])

        self.add_step("Create a token", "Create a short-lived token", [
            steps(f"Open the {link('https://developers.facebook.com/tools/explorer', 'Graph API Explorer')}.",
                  "At the right, under <b>Meta App</b>, choose the app you just made.",
                  "Under <b>User or Page</b> choose <b>Get User Access Token</b>.",
                  f"Under <b>Permissions</b> add exactly these: {perms}.",
                  "Click <b>Generate Access Token</b>. In the window that opens, choose <b>only the Page</b> you "
                  "want to stream to, and confirm.",
                  "Copy the long text in the <b>Access Token</b> box. You paste it in the next step."),
            ui.callout("Only what is needed",
                       "These three permissions let the app see which Pages you manage and create posts (the "
                       "scheduled live video) on the Page you pick. Do not add others. The token you copy works "
                       "for about an hour, and the app does not keep it.")])

        self.app_id = QLineEdit()
        self.app_id.setPlaceholderText("App ID  (numbers)")
        self.app_secret = secret_field("App secret")
        self.user_token = secret_field("Access token from the Graph API Explorer")
        self.find_button = ui.button("Find my Pages", "primary", self.find_pages)
        self.find_state = ui.label("", "sub", wrap=True)
        find_row = QWidget()
        r = QHBoxLayout(find_row)
        r.setContentsMargins(0, 0, 0, 0)
        r.addWidget(self.find_button)
        r.addWidget(self.find_state, 1)
        self.page = QComboBox()
        self.page.setEnabled(False)
        self.page.addItem("Your Pages appear here")
        self.add_step("Connect", "Connect the Page", [
            ui.rich("Paste the three values and click <b>Find my Pages</b>. The app trades the short-lived token "
                    "for a lasting key for your Page."),
            self.app_id, self.app_secret, self.user_token, find_row, self.page,
            ui.callout("What is kept, and what is not",
                       f"Kept, in {vault.where()}: the access key of the Page you choose. <b>Not kept:</b> the App "
                       "secret and the token you pasted. They are used once, now, and then forgotten.")],
            check=lambda: "" if self.found else "Click 'Find my Pages' first.")

        self.add_step("Go public", "One last thing on Meta's side", [
            ui.rich("A new Meta app starts in <b>Development</b> mode. In that mode, what the app posts can be "
                    "seen <b>only by you</b> and others who have a role on the app, not by your audience."),
            steps("In the Meta app, open <b>App settings → Basic</b> and enter a <b>Privacy policy URL</b> (your "
                  "organisation's website privacy page will do).",
                  "Switch <b>App mode</b> from Development to <b>Live</b> (in newer dashboards: <b>Publish</b>).",
                  "No app review is needed: you only use the app for a Page you manage yourself."),
            ui.callout("Check the first one",
                       "After the first stream is scheduled, look at your Page while signed out (or ask someone "
                       "else) to make sure the announcement is visible. The app asks Facebook to use your Page's "
                       "<b>persistent stream key</b> for every stream, so your encoder keeps one key. Confirm on "
                       "the first stream that your usual key takes it live; if not, the History page shows why "
                       "and lets you copy that stream's own key.", "warn", "warn")])
        self.ready()

    def find_pages(self):
        self.error.setText("")
        app_id, secret, token = self.app_id.text(), self.app_secret.text(), self.user_token.text()
        if not app_id.strip().isdigit() or len(secret.strip()) < 10 or len(token.strip()) < 20:
            self.error.setText("Fill in the App ID (numbers only), the App secret and the access token.")
            return
        problem = self.vault.available()
        if problem:
            self.error.setText(problem)
            return
        self.find_button.setEnabled(False)
        self.find_state.setText("Asking Facebook ...")
        ui.run_async(lambda: facebook.pages(app_id, secret, token), self.pages_found)

    def pages_found(self, pages, error):
        self.find_button.setEnabled(True)
        self.find_state.setText("")
        if error:
            self.error.setText(str(error))
            return
        if not pages:
            self.error.setText("The token gives access to no Page. In step 3, choose your Page when the "
                               "window asks which Pages the app may use.")
            return
        self.found = pages
        self.page.clear()
        for p in pages:
            self.page.addItem(p["name"], p["id"])
        self.page.setEnabled(True)
        self.find_state.setText(f"✓  Found {len(pages)} Page{'s' if len(pages) != 1 else ''}. Choose one below.")
        self.app_secret.clear()   # used; forget them
        self.user_token.clear()

    def finish(self):
        page = self.found[self.page.currentIndex()]
        dest = {"id": new_id(), "kind": "facebook", "name": page["name"], "account_id": page["id"],
                "options": {"persistent_key": True}}
        try:
            self.vault.set(dest["id"], "page_token", page["token"])
        except VaultError as exc:
            return str(exc)
        self.found = []
        self.store.destinations.append(dest)
        self.store.save()
        self.destination = dest
        return ""
