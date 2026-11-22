"""The step-by-step guides: connecting a destination (a YouTube channel, a website), connecting OBS on
this or another computer, and setting up a way to be told (email, Discord, Slack, Pushover).

Each guide explains what to click on the platform's own pages, says why each step is safe, and ends
by saving the sign-in in the system keychain (vault.py). Nothing is saved before the last step.
"""
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

import facebook
import net
import notify
import obs
import obslaunch
import ui
import webhook
import wordpress
import youtube
from store import new_id
from vault import NOTIFY, MemoryVault, VaultError


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


def field_grid(rows):
    """Names at the left, their fields at the right, as one widget."""
    box = QWidget()
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(8)
    for i, (text, widget) in enumerate(rows):
        grid.addWidget(ui.label(text, "strong"), i, 0)
        grid.addWidget(widget, i, 1)
    return box


def action_row(button, state):
    """A button with a line of words at its right (what it is doing, or what it found)."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(button)
    row.addWidget(state, 1)
    return box


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
        self.latency = QComboBox()
        for key, text in youtube.LATENCY:
            self.latency.addItem(text, key)
        self.latency.setCurrentIndex(max(0, self.latency.findData(options.get("latency") or "normal")))
        self.category = QComboBox()
        for key, text in youtube.CATEGORIES:
            self.category.addItem(text, key)
        self.category.setCurrentIndex(max(0, self.category.findData(str(options.get("category") or ""))))
        self.playlist = QLineEdit(options.get("playlist", ""))
        self.playlist.setPlaceholderText("Optional: paste a playlist's link from YouTube")
        self.playlist.setMinimumWidth(340)
        rows = [("Who can watch", self.privacy, "A schedule can say otherwise for its own streams."),
                ("Stream key", self.stream, "With a key chosen, your encoder (OBS, ATEM ...) keeps the same key every week."),
                ("Made for kids", self.kids, "YouTube requires an answer. Most services and events are not."),
                ("Start and stop by itself", self.auto,
                 "The broadcast goes live when your encoder starts sending, and ends when it stops."),
                ("Delay", self.latency, "How far viewers are behind the camera. Lower delays mean lower picture "
                                        "quality, and ultra low has no captions or 1440p and above."),
                ("Category", self.category, ""),
                ("Playlist", self.playlist, "Every new stream is added to it. A schedule can name another one.")]
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
                "auto_stop": self.auto.isChecked(), "latency": self.latency.currentData(),
                "category": self.category.currentData(), "playlist": self.playlist.text().strip()}

    def problem(self):
        """A sentence when something typed here cannot work ("" when all is well)."""
        if self.playlist.text().strip() and not youtube.playlist_id(self.playlist.text()):
            return "The playlist is not understood. Paste the playlist's link from YouTube, or leave it empty."
        return ""


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

        self.add_step("Sign-in screen", "Set up the sign-in screen", [
            steps(f"Open {link('https://console.cloud.google.com/auth/overview', 'Google Auth Platform')} and click "
                  "<b>Get started</b>.",
                  "App name: <b>Stream Scheduler</b>. User support email: your own address.",
                  "Audience: <b>External</b>.",
                  "Contact information: your email address. Agree to the policy and click <b>Create</b>."),
            ui.callout("Why 'External'", "External means any Google account can be allowed to sign in, which "
                       "includes the account that owns your channel. Nobody can use your project without the "
                       "client secret you create in step 6 and your own Google login.")])

        self.add_step("Branding", "Fill in the Branding page", [
            ui.rich("Google will not let you publish the app until its <b>Branding</b> page is complete. For that "
                    "you need a web page on <b>a domain you own</b>, such as your organisation's website. Pages on "
                    "shared platforms (Google Sites, Facebook, a github.io address) are refused."),
            steps("On your website, make (or choose) a <b>home page</b> for this use. It must be open to everyone "
                  "without logging in, say what the app does (it schedules your live streams on YouTube), say why "
                  "it asks for access to your YouTube account (to create those scheduled streams), and link to "
                  "your privacy policy.",
                  "Have a <b>privacy policy</b> page on the same domain. It should say what the app does with "
                  "YouTube data: it creates your scheduled broadcasts, and keeps its sign-in on your computer only.",
                  f"Prove the domain is yours: open {link('https://search.google.com/search-console', 'Google Search Console')} "
                  "with the same Google account, choose <b>Add property → Domain</b>, enter your domain, and add "
                  "the <b>TXT record</b> it shows at your domain's DNS provider. Click <b>Verify</b>.",
                  "In Google Auth Platform open <b>Branding</b>. Enter the <b>Application home page</b> and the "
                  "<b>Application privacy policy link</b>, and under <b>Authorized domains</b> add your domain "
                  "(for example <b>example.org</b>, without www).",
                  "Logo: optional. If you add one it must be square, 120 × 120 pixels, under 1 MB. The terms of "
                  "service link can stay empty.",
                  "Click <b>Save</b>. If Google reports a branding verification issue, fix what it names, wait "
                  "24 hours as it asks, and choose <b>I have fixed the issues</b>."),
            ui.callout("No website of your own?",
                       "You can skip this step and stay in <b>Testing</b>: on the Audience page add your own Google "
                       "address under <b>Test users</b>. Everything works, but Google ends the sign-in every 7 days, "
                       "so you would have to connect the channel again each week.", "warn", "warn")])

        self.add_step("Publish", "Publish the app", [
            steps("Open <b>Audience</b> at the left.",
                  "Click <b>Publish app</b> and confirm, so the publishing status reads <b>In production</b>.",
                  "If the button is greyed out, the Branding page is not complete yet: go back one step."),
            ui.callout("Do not skip this",
                       "While the status is <b>Testing</b>, Google ends every sign-in after 7 days and your "
                       "streams would stop being scheduled. Publishing does not make anything public: only someone "
                       "with your client secret (next step) and your Google login can use it.", "warn", "warn"),
            ui.callout("Waiting for Google's verification is fine",
                       "You can go on while Google is still checking your branding. Until it has finished, the "
                       "sign-in shows a warning that the app is not verified; step 7 says how to continue.")])

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
            check=lambda: (self.options.problem() if self.options else "") if self.tokens
            else "Sign in with Google first.")
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
        self.options = YouTubeOptions(getattr(self, "defaults", None), streams=streams)
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
                  "Check it: type <b>me/accounts</b> in the address line at the top and click <b>Submit</b>. Your "
                  "Page should be listed. If the list is empty and the Page is managed in a Meta <b>business "
                  "portfolio</b> (Business Suite), also add the permission <b>business_management</b> and "
                  "generate the token again.",
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
            check=self.check_pages)

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

    def check_pages(self):
        """Next on the Connect step: with no Pages yet, look for them instead of only saying so."""
        if self.found:
            return ""
        if self.find_button.isEnabled():
            self.find_pages()
        return self.error.text() or "Looking for your Pages ... choose one when they appear, then click Next."

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
            self.error.setText("The token gives access to no Page. Go back to step 3: choose your Page when the "
                               "window asks which Pages the app may use and, if the Page belongs to a business "
                               "portfolio, also add the permission business_management. Then paste the new token.")
            return
        self.found = pages
        self.page.clear()
        for p in pages:
            self.page.addItem(p["name"], p["id"])
        self.page.setEnabled(True)
        self.find_state.setText(f"✓  Found {len(pages)} Page{'s' if len(pages) != 1 else ''}. Choose one below, "
                                "then click Next.")
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


class WixWizard(Wizard):
    def __init__(self, parent, store, vault):
        super().__init__(parent, "Connect a Wix website", "wix")
        self.store, self.vault = store, vault
        self.found = []
        self.destination = None

        self.add_step("Before you start", "Show the stream on your Wix website", [
            ui.rich("After a schedule creates its YouTube stream, Stream Scheduler can put that stream on a page "
                    "of your Wix site, so the YouTube element there always shows the coming service."),
            ui.rich("Wix does not let an outside app edit an element on a page. The supported way is Wix's own "
                    "<b>CMS</b>: a small collection holds the stream's link, the YouTube element on your page is "
                    "connected to it, and the app only changes the link. You set this up once, in about 15 minutes."),
            steps("You must be the <b>owner or a co-owner</b> of the Wix site: only they can create API keys.",
                  "The schedule must also send to a <b>YouTube</b> channel. The website shows that stream.",
                  "Your page needs Wix's <b>YouTube</b> element where the stream should show. If it has one "
                  "today, it stays."),
            ui.callout("How this keeps your website safe",
                       f"The app keeps one API key, in <b>{vault.where()}</b>, encrypted with your login. In step 4 "
                       "you give the key only the permission to edit collection content, so it cannot change your "
                       "site's design, pages, members or payments. You can delete the key in Wix at any time.")])

        self.add_step("Make a collection", "Make a collection for the stream", [
            steps(f"Open your site's dashboard at {link('https://manage.wix.com')} and choose <b>CMS</b> in the menu "
                  "at the left.",
                  "Click <b>Create Collection</b> and start from scratch. Name it <b>Livestream</b>. Its "
                  "<b>Collection ID</b> is then also <b>Livestream</b>.",
                  "Wix adds a few fields by itself (Title, Description, Image ...). Keep <b>Title</b>; the others "
                  "do no harm and can stay empty.",
                  "Click <b>+ Add Field</b> at the right end of the column headers. Choose the type <b>URL</b> and "
                  "name it <b>Video URL</b>. In the same panel, check that its <b>Field ID</b> reads "
                  "<b>videoUrl</b>.",
                  "Click <b>+ Add Item</b>. Give it a <b>Title</b> you will recognise, for example <b>Sunday "
                  "stream</b>, and any YouTube link as Video URL for now. The app replaces the link each week and "
                  "leaves the Title alone.",
                  "Check that the item's <b>Status</b> is <b>Published</b>, and under <b>More Actions → Permissions "
                  "& privacy</b> that everyone can view the content.",
                  "Optional: if the page should also show the stream's title, add a <b>Text</b> field named "
                  "<b>Stream title</b> (Field ID <b>streamTitle</b>) for the app to write it in."),
            ui.callout("Good to know", "What is in a collection is live as soon as it changes. That is why the "
                       "website shows the new stream without anyone publishing the site.")])

        self.add_step("Connect the element", "Connect the YouTube element on your page", [
            steps("Open the site in the <b>Wix Editor</b> and go to the page that shows the stream.",
                  "Use Wix's <b>YouTube</b> element (the one your page probably has already). Do <b>not</b> use "
                  "Wix's own <b>Video Player</b>: it cannot show a stream that has not started yet and plays its "
                  "sample video instead.",
                  "Select the YouTube element and click the <b>Connect to CMS</b> icon. Click <b>Create "
                  "Dataset</b>, choose the <b>Livestream</b> collection and click <b>Create</b>.",
                  "Open <b>Dataset Settings</b> and set <b>Dataset mode</b> to <b>Read</b>. In Write mode the "
                  "element shows nothing from the collection, and Filter is greyed out.",
                  "Under <b>Filter</b>, click <b>Add Filter</b> and choose <b>Title</b> <b>is</b> the Title of "
                  "your item, written exactly as in the collection.",
                  "Back under <b>Connections</b>, connect the element's video link to the <b>Video URL</b> field.",
                  "Click <b>Preview</b>: the element should show the link from your collection item. (The editor "
                  "itself keeps showing the element's own sample video.)",
                  "Click <b>Publish</b>. This is the only time the site has to be published for this."),
            ui.callout("Two services, two elements?",
                       "Give the collection one item per service (for example Title <b>8:15 service</b> and "
                       "<b>10:30 service</b>) and each YouTube element its own dataset, filtered to its item. Then "
                       "add this Wix destination once per element, choosing a different item each time, and tick "
                       "one in each schedule.")])

        self.add_step("Create an API key", "Create an API key", [
            steps(f"Open {link('https://manage.wix.com/account/api-keys')} (owner or co-owner only).",
                  "Click <b>Generate API Key</b>. Name it <b>Stream Scheduler</b>.",
                  "Under <b>Permissions</b>, open <b>All site permissions</b> and tick <b>Wix Data</b>. Leave "
                  "everything else unticked.",
                  "Only if you want the app to publish the site as well (see the next step): Wix currently lists "
                  "the permission <b>Manage SEO Settings</b> for publishing a site.",
                  "Click <b>Generate Key</b>, confirm with the code Wix emails you, and <b>copy the key</b>. Wix "
                  "shows it only once.",
                  "Find the <b>Site ID</b>: open your site's dashboard and look at the address. In "
                  "<b>manage.wix.com/dashboard/<u>xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx</u>/home</b> the underlined "
                  "part is the Site ID."),
            ui.callout("Treat the API key like a password",
                       f"It is saved in {vault.where()}, not in a file. Do not email it or put it in a shared "
                       "document. If it ever leaks, delete it on the API keys page and make a new one.")])

        self.api_key = secret_field("API key")
        self.site_id = QLineEdit()
        self.site_id.setPlaceholderText("Site ID  (from the dashboard's address)")
        self.collection = QLineEdit("Livestream")
        self.url_field = QLineEdit("videoUrl")
        self.title_field = QLineEdit()
        self.title_field.setPlaceholderText("Optional, e.g. streamTitle. Empty: the app does not write the title.")
        self.page_url = QLineEdit()
        self.page_url.setPlaceholderText("Optional: the page's address, for the Open button (https://...)")
        self.name = QLineEdit("Website")
        grid_box = QWidget()
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        rows = [("Name in this app", self.name), ("API key", self.api_key), ("Site ID", self.site_id),
                ("Collection ID", self.collection), ("Field key of the video link", self.url_field),
                ("Field key for the stream's title", self.title_field), ("Page", self.page_url)]
        for i, (text, widget) in enumerate(rows):
            grid.addWidget(ui.label(text, "strong"), i, 0)
            grid.addWidget(widget, i, 1)
        self.find_button = ui.button("Find my collection", "primary", self.find_items)
        self.find_state = ui.label("", "sub", wrap=True)
        find_row = QWidget()
        r = QHBoxLayout(find_row)
        r.setContentsMargins(0, 0, 0, 0)
        r.addWidget(self.find_button)
        r.addWidget(self.find_state, 1)
        self.item = QComboBox()
        self.item.setEnabled(False)
        self.item.addItem("The collection's items appear here")
        self.publish = ui.Switch(False)
        publish_row = QWidget()
        r = QHBoxLayout(publish_row)
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(10)
        r.addWidget(self.publish)
        r.addWidget(ui.label("Also publish the site after each update", "strong"), 1)
        self.add_step("Connect", "Connect the website", [
            grid_box, find_row, self.item, publish_row,
            ui.callout("Publishing is usually not needed, and it publishes everything",
                       "The new stream shows on the website without publishing. If you switch this on, Wix "
                       "publishes <b>every change saved in the editor</b>, including a half-finished edit someone "
                       "else left there. Leave it off unless your page does not update without it.", "warn", "warn")],
            check=self.check_items)
        self.ready()

    def values(self):
        return {"collection": self.collection.text().strip(), "url_field": self.url_field.text().strip(),
                "title_field": self.title_field.text().strip(), "page_url": self.page_url.text().strip(),
                "publish": self.publish.isChecked()}

    def check_items(self):
        if self.found:
            return ""
        if self.find_button.isEnabled():
            self.find_items()
        return self.error.text() or "Looking for your collection ... choose the item when it appears, then click Finish."

    def find_items(self):
        self.error.setText("")
        key, site, v = self.api_key.text().strip(), self.site_id.text().strip(), self.values()
        if len(key) < 20 or len(site) < 20 or not v["collection"] or not v["url_field"]:
            self.error.setText("Fill in the API key, the Site ID, the collection ID and the field key of the video link.")
            return
        problem = self.vault.available()
        if problem:
            self.error.setText(problem)
            return
        self.find_button.setEnabled(False)
        self.find_state.setText("Asking Wix ...")
        import wix
        ui.run_async(lambda: wix.items(key, site, v["collection"]), self.items_found)

    def items_found(self, items, error):
        self.find_button.setEnabled(True)
        self.find_state.setText("")
        if error:
            self.error.setText(str(error))
            return
        if not items:
            self.error.setText("The collection has no items. Add one item to it in the Wix CMS (step 2), then try again.")
            return
        self.found = items
        self.item.clear()
        for i in items:
            self.item.addItem(str(i["data"].get("title") or i["id"]), i["id"])
        self.item.setEnabled(True)
        known = set().union(*(i["data"].keys() for i in items))
        v = self.values()
        missing = [f for f in (v["url_field"], v["title_field"]) if f and f not in known]
        self.find_state.setText(
            f"✓  Found {len(items)} item{'s' if len(items) != 1 else ''}. Choose one below, then click Finish."
            + (f"  Note: no item has a value in “{missing[0]}” yet; check that field key." if missing else ""))

    def finish(self):
        dest = {"id": new_id(), "kind": "wix", "name": self.name.text().strip() or "Website",
                "account_id": self.site_id.text().strip(),
                "options": {**self.values(), "item_id": self.item.currentData(),
                            "item_title": self.item.currentText()}}
        try:
            self.vault.set(dest["id"], "api_key", self.api_key.text().strip())
        except VaultError as exc:
            return str(exc)
        self.api_key.clear()
        self.store.destinations.append(dest)
        self.store.save()
        self.destination = dest
        return ""


class WordPressWizard(Wizard):
    def __init__(self, parent, store, vault):
        super().__init__(parent, "Connect a WordPress website", "wordpress")
        self.store, self.vault = store, vault
        self.found = []
        self.destination = None

        self.add_step("Before you start", "Show the stream on your WordPress website", [
            ui.rich("After a schedule creates its YouTube stream, Stream Scheduler can put that stream on a page "
                    "of your WordPress site, so the page always shows the coming service."),
            ui.rich("It works through a <b>synced pattern</b>: a block you place on your page once. The app "
                    "replaces what is inside that pattern with the new YouTube video, and touches nothing else "
                    "on the page. You set this up once, in about ten minutes."),
            steps("WordPress <b>5.6 or newer</b>, on an address that starts with <b>https://</b>.",
                  "A WordPress user with the role <b>Editor</b> or <b>Administrator</b>.",
                  "The schedule must also send to a <b>YouTube</b> channel. The website shows that stream.",
                  "On WordPress.com this needs a plan that allows plugins; a site you host yourself has it "
                  "already."),
            ui.callout("How this keeps your website safe",
                       f"The app keeps one <b>application password</b>, in <b>{vault.where()}</b>, encrypted "
                       "with your login. It is not your WordPress password: it cannot be used to log in to the "
                       "dashboard, and you can revoke it in your profile at any time."),
            ui.callout("Not tried on a real site yet",
                       "This guide follows WordPress's documented way of working, but it has not been confirmed "
                       "on a live website. Check the page after the first stream is scheduled.", "warn", "warn")])

        self.add_step("Make the pattern", "Put a synced pattern on your page", [
            steps("In the WordPress dashboard, open the page that should show the stream, in the editor.",
                  "Where the video should be, add a <b>YouTube</b> block (type <b>/youtube</b>) and paste any "
                  "YouTube link for now.",
                  "Select the block, open its <b>Options</b> menu (the three dots) and choose <b>Create "
                  "pattern</b>.",
                  "Name it <b>Livestream</b>, leave <b>Synced</b> switched on, and click <b>Create</b> (older "
                  "versions call this <b>Create Reusable block</b>).",
                  "Click <b>Update</b> (or <b>Publish</b>) to save the page."),
            ui.callout("Why 'Synced'", "A synced pattern shows the same content everywhere it is placed, and "
                       "changes when the pattern changes. That is what lets the app update your page without "
                       "editing the page itself. A pattern that is not synced is only a copy.")])

        self.add_step("Application password", "Create an application password", [
            steps("In the dashboard, open <b>Users → Profile</b> (your own profile).",
                  "Scroll down to <b>Application Passwords</b>.",
                  "Type the name <b>Stream Scheduler</b> and click <b>Add New Application Password</b>.",
                  "Copy the password WordPress shows (six groups of four letters). It is shown only once.",
                  "Note your <b>user name</b>: it is at the top of the same page."),
            ui.callout("No 'Application Passwords' section?",
                       "WordPress hides it when the site does not use https, and some security plugins switch "
                       "it off. Ask whoever looks after the site to enable application passwords.", "warn", "warn"),
            ui.callout("Treat it like a password",
                       f"It is saved in {vault.where()}, not in a file. If it ever leaks, click <b>Revoke</b> "
                       "next to it in your profile and make a new one.")])

        self.name = QLineEdit("Website")
        self.site = QLineEdit()
        self.site.setPlaceholderText("https://www.example.org")
        self.user = QLineEdit()
        self.user.setPlaceholderText("Your WordPress user name")
        self.password = secret_field("Application password")
        self.page_url = QLineEdit()
        self.page_url.setPlaceholderText("Optional: the page's address, for the Open button (https://...)")
        self.find_button = ui.button("Find my patterns", "primary", self.find)
        self.find_state = ui.label("", "sub", wrap=True)
        self.pattern = QComboBox()
        self.pattern.setEnabled(False)
        self.pattern.addItem("The site's synced patterns appear here")
        self.show_title = ui.Switch(False)
        self.add_step("Connect", "Connect the website", [
            field_grid([("Name in this app", self.name), ("Website address", self.site), ("User name", self.user),
                        ("Application password", self.password), ("Page", self.page_url)]),
            action_row(self.find_button, self.find_state), self.pattern,
            ui.toggle_row(self.show_title, "Also write the stream's title above the video"),
            ui.callout("If the page does not change",
                       "A caching plugin or service can keep showing the old page for a while. Clear its cache "
                       "once, or exclude this page from caching.")],
            check=self.check)
        self.ready()

    def check(self):
        if self.found:
            return ""
        if self.find_button.isEnabled():
            self.find()
        return self.error.text() or "Looking for your patterns ... choose one when they appear, then click Finish."

    def find(self):
        self.error.setText("")
        site, user, password = self.site.text(), self.user.text().strip(), self.password.text().strip()
        try:
            wordpress.site_address(site)
        except net.ApiError as exc:
            self.error.setText(str(exc))
            return
        if not user or len(password) < 8:
            self.error.setText("Fill in the user name and the application password.")
            return
        problem = self.vault.available()
        if problem:
            self.error.setText(problem)
            return
        self.find_button.setEnabled(False)
        self.find_state.setText("Asking WordPress ...")
        ui.run_async(lambda: wordpress.patterns(site, user, password), self.found_patterns)

    def found_patterns(self, patterns, error):
        self.find_button.setEnabled(True)
        self.find_state.setText("")
        if error:
            self.error.setText(str(error))
            return
        if not patterns:
            self.error.setText("The site has no synced pattern yet. Make one (step 2), then try again.")
            return
        self.found = patterns
        self.pattern.clear()
        for p in patterns:
            self.pattern.addItem(p["title"], p["id"])
        self.pattern.setEnabled(True)
        self.find_state.setText(f"✓  Found {len(patterns)} pattern{'s' if len(patterns) != 1 else ''}. Choose "
                                "yours below, then click Finish.")

    def finish(self):
        dest = {"id": new_id(), "kind": "wordpress", "name": self.name.text().strip() or "Website",
                "account_id": wordpress.site_address(self.site.text()),
                "options": {"user": self.user.text().strip(), "pattern_id": self.pattern.currentData(),
                            "pattern_title": self.pattern.currentText(), "show_title": self.show_title.isChecked(),
                            "page_url": self.page_url.text().strip()}}
        try:
            self.vault.set(dest["id"], "app_password", self.password.text().strip())
        except VaultError as exc:
            return str(exc)
        self.password.clear()
        self.store.destinations.append(dest)
        self.store.save()
        self.destination = dest
        return ""


class WebhookWizard(Wizard):
    def __init__(self, parent, store, vault):
        super().__init__(parent, "Connect a web address", "webhook")
        self.store, self.vault = store, vault
        self.destination = None
        sample = ("{\n  \"event\": \"stream.scheduled\",\n  \"title\": \"Sunday Service - November 14, 2027\",\n"
                  "  \"description\": \"Join us live this Sunday.\",\n"
                  "  \"url\": \"https://www.youtube.com/watch?v=abc123\",\n  \"video_id\": \"abc123\",\n"
                  "  \"start\": \"2027-11-14T14:00:00Z\",\n  \"start_local\": \"2027-11-14T08:00\",\n"
                  "  \"schedule\": \"Sunday Service\"\n}")
        shown = ui.label(sample)
        shown.setFont(ui.fixed_font(9))
        shown.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.add_step("How it works", "Tell another service about each new stream", [
            ui.rich("For a website this app has no guide for (Squarespace, Webflow, a site of your own ...), or "
                    "for anything else that should happen when a stream is scheduled. Each time a schedule's "
                    "YouTube stream is created, the app sends its details to a web address you give it. A "
                    "service at that address does the rest."),
            steps("In an automation service, make a step that <b>receives a webhook</b>: in "
                  f"{link('https://zapier.com', 'Zapier')} choose <b>Webhooks by Zapier → Catch Hook</b>; in "
                  f"{link('https://www.make.com', 'Make')} choose <b>Webhooks → Custom webhook</b>.",
                  "The service shows a <b>web address</b> for it. Copy it for the next step.",
                  "After the test in the next step, the service knows the fields below and you can use them in "
                  "its following steps, for example to update a page or post a message."),
            ui.label("WHAT IS SENT (as JSON, by POST)", "caps"), shown,
            ui.callout("The address is kept like a password",
                       f"Anyone who knows the address can send to it, so it is saved in {vault.where()}, not in "
                       "the settings file. Only addresses that start with https:// are accepted.")])

        self.name = QLineEdit("Webhook")
        self.url = secret_field("https://hooks.example.com/...")
        self.test_button = ui.button("Send a test", "primary", self.test)
        self.test_state = ui.label("", "sub", wrap=True)
        self.add_step("Connect", "Paste the web address", [
            field_grid([("Name in this app", self.name), ("Web address", self.url)]),
            action_row(self.test_button, self.test_state),
            ui.rich("The test sends the same fields with <b>\"event\": \"test\"</b> and made-up values, so the "
                    "service can learn them. Real streams send <b>\"event\": \"stream.scheduled\"</b>."),
            ui.callout("The schedule must also send to YouTube",
                       "The web address is told about the YouTube stream of a schedule, after it was created. "
                       "Tick both the YouTube channel and this address in the schedule.")],
            check=self.check)
        self.ready()

    def check(self):
        try:
            webhook.address(self.url.text())
        except net.ApiError as exc:
            return str(exc)
        return self.vault.available()

    def test(self):
        self.error.setText(self.check())
        if self.error.text():
            return
        url = self.url.text()
        self.test_button.setEnabled(False)
        self.test_state.setText("Sending ...")
        from datetime import datetime, timezone
        now = datetime.now()
        data = webhook.payload("Sunday Service - test", "A test from Stream Scheduler.",
                               "https://www.youtube.com/watch?v=test", now.astimezone(timezone.utc), now, "Test", True)

        def done(_, error):
            self.test_button.setEnabled(True)
            self.test_state.setText("" if error else "✓  Sent. Look for it in the service.")
            self.error.setText(str(error) if error else "")
        ui.run_async(lambda: webhook.send(url, data), done)

    def finish(self):
        dest = {"id": new_id(), "kind": "webhook", "name": self.name.text().strip() or "Webhook",
                "account_id": "", "options": {}}
        try:
            self.vault.set(dest["id"], "url", self.url.text().strip())
        except VaultError as exc:
            return str(exc)
        self.url.clear()
        self.store.destinations.append(dest)
        self.store.save()
        self.destination = dest
        return ""


class ObsWizard(Wizard):
    """Connect OBS on this computer or another one on the network (an "encoder"), so the app can look
    at it before a service. It only reads from OBS; it never starts a stream or changes a setting."""

    def __init__(self, parent, store, vault, existing=None):
        super().__init__(parent, "Connect OBS", "obs")
        self.store, self.vault = store, vault
        self.destination = None   # the encoder, once saved (the name the other guides use)
        self.found = None

        self.add_step("Before you start", "Let Stream Scheduler look at OBS", [
            ui.rich("Stream Scheduler can look at OBS Studio before a service, to see that it is open and "
                    "ready. OBS can be on <b>this computer</b> or on <b>another computer on the same network</b>, "
                    "such as a second streaming PC."),
            ui.rich("It only <b>looks</b>. It never starts or stops a stream, switches a scene or changes a "
                    "setting in OBS: going live stays with the people at the computer."),
            steps("<b>OBS Studio 28 or newer.</b> Its remote control (the WebSocket server) is built in.",
                  "For another computer: its <b>name or address</b> on the network, such as 192.168.1.20.",
                  "About five minutes."),
            ui.callout("How this keeps the streaming computer safe",
                       f"OBS's remote control is protected by a password, which the app keeps in "
                       f"<b>{vault.where()}</b>, encrypted with your login. The connection is not encrypted, "
                       "so it is for your own network only: never open port 4455 to the internet on your "
                       "router. To reach OBS at another site, use a VPN such as Tailscale.")])

        self.add_step("In OBS", "Switch on OBS's remote control", [
            steps("On the computer with OBS, open <b>OBS Studio</b>.",
                  "Choose <b>Tools → WebSocket Server Settings</b>.",
                  "Tick <b>Enable WebSocket server</b>.",
                  "Leave <b>Enable Authentication</b> ticked, so a password is needed. OBS makes one for you.",
                  "Leave the <b>Server Port</b> at <b>4455</b> unless you have a reason to change it.",
                  "Click <b>Show Connect Info</b> and keep it open: it shows the address, port and password "
                  "for the next step. Then click <b>OK</b>."),
            ui.callout("OBS on another computer",
                       "When the WebSocket server is switched on, Windows may ask whether OBS may use the "
                       "network. Allow it on <b>private networks</b> only. If you missed that question, allow "
                       "<b>OBS Studio</b> in Windows Security → Firewall & network protection → Allow an app "
                       "through firewall.", "warn", "warn")])

        self.place = QComboBox()
        self.place.addItem("This computer", "local")
        self.place.addItem("Another computer on the network", "remote")
        self.name = QLineEdit("OBS on this computer")
        self.host = QLineEdit()
        self.host.setPlaceholderText("Its name or address, such as 192.168.1.20")
        self.port = QLineEdit(str(obs.DEFAULT_PORT))
        self.password = secret_field("The password from Show Connect Info")
        self.fill_button = ui.button("Fill in from OBS on this computer", "", self.fill_in,
                                     "Read the port and password from OBS's own settings on this computer")
        self.fill_state = ui.label("", "sub", wrap=True)
        self.fill_row = action_row(self.fill_button, self.fill_state)
        self.program = (existing or {}).get("program", "")
        self.program_button = ui.button("Choose ...", "", self.choose_program,
                                        "Choose the OBS program, if it is not where OBS installs itself")
        self.program_state = ui.label("", "sub", wrap=True)
        self.program_row = action_row(self.program_button, self.program_state)
        self.test_button = ui.button("Connect to OBS", "primary", self.test)
        self.test_state = ui.label("", "sub", wrap=True)
        self.fill_note = ui.rich("<b>Fill in</b> reads the port and password from OBS's own settings on this "
                                 "computer, so you need not copy them. Nothing else of OBS's is read.")
        self.add_step("Connect", "Connect to OBS", [
            field_grid([("OBS is on", self.place), ("Name in this app", self.name), ("Computer", self.host),
                        ("Port", self.port), ("Password", self.password)]),
            self.fill_row, action_row(self.test_button, self.test_state), self.fill_note, self.program_row,
            ui.callout("Stream Scheduler in Docker",
                       "Choose <b>Another computer on the network</b> and type the address of the computer "
                       "with OBS: the container is a computer of its own.")],
            check=self.check)
        self.place.currentIndexChanged.connect(self.placed)
        for edit in (self.host, self.port, self.password):
            edit.textChanged.connect(self.changed)
        if existing:
            self.place.setCurrentIndex(0 if existing.get("local") else 1)
            self.name.setText(existing.get("name", ""))
            if not existing.get("local"):
                self.host.setText(existing.get("host", ""))
            self.port.setText(str(existing.get("port", obs.DEFAULT_PORT)))
        self.placed()
        self.ready()

    def local(self):
        return self.place.currentData() == "local"

    def placed(self):
        local = self.local()
        self.host.setEnabled(not local)
        if local:
            self.host.clear()
            self.host.setPlaceholderText("This computer")
        else:
            self.host.setPlaceholderText("Its name or address, such as 192.168.1.20")
        self.fill_row.setVisible(local)
        self.fill_note.setVisible(local)
        self.program_row.setVisible(local)
        self.show_program()
        names = ("OBS on this computer", "OBS on another computer", "OBS")
        if self.name.text().strip() in names or not self.name.text().strip():
            self.name.setText(names[0] if local else names[1])
        self.changed()

    def show_program(self):
        found = obslaunch.find(self.program)
        if found:
            where = "chosen by you" if self.program else "found"
            self.program_state.setText(f"OBS program ({where}): {found.replace('flatpak:', 'Flatpak ')}. "
                                       "Schedules can open it before a service.")
        else:
            self.program_state.setText("The OBS program was not found where OBS installs itself. Choose it, so "
                                       "schedules can open OBS before a service (optional).")

    def choose_program(self):
        from PySide6.QtWidgets import QFileDialog
        kind = {"win32": "OBS (obs64.exe)", "darwin": "OBS (OBS.app)"}.get(sys.platform, "OBS (obs)")
        path, _ = QFileDialog.getOpenFileName(self, "Choose the OBS program", self.program or "", f"{kind} (*)")
        if path:
            self.program = path
            self.show_program()

    def changed(self):
        self.found = None
        self.test_state.setText("")

    def target(self):
        """(host, port) from the fields, or ObsError."""
        if self.local():
            host = obs.LOCAL
        else:
            host, port = obs.address(self.host.text())
            if self.host.text().strip().count(":") == 1:   # "192.168.1.20:4456": the port typed with it wins
                return host, port
        text = self.port.text().strip()
        if not text.isdigit() or not 0 < int(text) < 65536:
            raise obs.ObsError("The port is a number, such as 4455.", reason="address")
        return host, int(text)

    def fill_in(self):
        found = obs.local_settings()
        if found is None:
            self.fill_state.setText("")
            self.error.setText("OBS's settings were not found on this computer. Is OBS 28 or newer installed "
                               "here? You can type the port and password instead.")
            return
        self.error.setText("")
        self.port.setText(str(found["port"]))
        self.password.setText(found["password"] if found["auth"] else "")
        self.fill_state.setText("✓  Filled in." if found["enabled"] else
                                "Filled in, but the WebSocket server is switched off in OBS: switch it on "
                                "(step 2), then connect.")

    def test(self):
        self.error.setText("")
        try:
            host, port = self.target()
        except obs.ObsError as exc:
            self.error.setText(str(exc))
            return
        password = self.password.text()
        self.test_button.setEnabled(False)
        self.test_state.setText("Connecting ...")
        ui.run_async(lambda: obs.info(host, port, password), self.tested)

    def tested(self, found, error):
        self.test_button.setEnabled(True)
        if error:
            self.found = None
            self.test_state.setText("")
            self.error.setText(str(error))
            return
        self.found = found
        self.error.setText("")
        self.test_state.setText(f"✓  Connected: {obs.describe(found)}. Click Finish to save.")

    def check(self):
        if self.found:
            return self.vault.available() if self.password.text() else ""
        if self.test_button.isEnabled():
            self.test()
        return self.error.text() or "Connecting to OBS ... click Finish when it says Connected."

    def finish(self):
        host, port = self.target()
        password = self.password.text()
        encoder = {"id": new_id(), "kind": "obs", "name": self.name.text().strip() or "OBS", "host": host,
                   "port": port, "local": self.local(), "auth": bool(password)}
        if self.local() and self.program:
            encoder["program"] = self.program
        if password:
            try:
                self.vault.set(encoder["id"], "password", password)
            except VaultError as exc:
                return str(exc)
        self.password.clear()
        self.store.encoders.append(encoder)
        self.store.save()
        self.destination = encoder
        return ""


# ---- ways to be told -----------------------------------------------------------------------

class NotifyWizard(Wizard):
    """A guide that sets up one way to be told. A subclass says which (`channel`), builds its steps, and
    gives what was typed: secrets() for the keychain, config() for the settings file, problem()."""
    channel = ""

    def __init__(self, parent, store, vault):
        super().__init__(parent, f"Set up {notify.CHANNELS[self.channel]}", self.channel)
        self.store, self.vault = store, vault
        self.old = dict(notify.settings(store)["channels"].get(self.channel, {}))
        self.test_button = ui.button("Send a test message", "primary", self.test)
        self.test_state = ui.label("", "sub", wrap=True)

    def test_row(self):
        return action_row(self.test_button, self.test_state)

    def secrets(self):
        raise NotImplementedError

    def config(self):
        return {}

    def problem(self):
        return ""

    def check(self):
        return self.problem() or self.vault.available()

    def test(self):
        self.error.setText(self.problem())
        if self.error.text():
            return
        once = MemoryVault()   # the test uses what is typed; nothing is saved before Finish
        for name, value in self.secrets().items():
            once.set(NOTIFY, name, value)
        config = self.config()
        self.test_button.setEnabled(False)
        self.test_state.setText("Sending ...")

        def done(_, error):
            self.test_button.setEnabled(True)
            self.test_state.setText("" if error else "✓  Sent. Check that it arrived, then click Finish.")
            self.error.setText(str(error) if error else "")
        ui.run_async(lambda: notify.send_one(
            self.channel, config, once, "Test from Stream Scheduler",
            "This is how you will be told when a stream needs you."), done)

    def finish(self):
        try:
            for name, value in self.secrets().items():
                self.vault.set(NOTIFY, name, value)
        except VaultError as exc:
            return str(exc)
        notify.settings(self.store)["channels"][self.channel] = {**self.config(), "on": True}
        self.store.save()
        return ""


class DiscordWizard(NotifyWizard):
    channel = "discord"

    def __init__(self, parent, store, vault):
        super().__init__(parent, store, vault)
        self.add_step("Make a webhook", "Make a webhook in Discord", [
            ui.rich("Messages arrive in a channel of your Discord server, from a sender called a "
                    "<b>webhook</b>. You need the permission <b>Manage Webhooks</b> on the server."),
            steps("In Discord, open the server and click its name, then <b>Server Settings</b>.",
                  "Open <b>Integrations</b>, then <b>Webhooks</b>, and click <b>New Webhook</b>.",
                  "Click the new webhook. Name it <b>Stream Scheduler</b> and choose the <b>channel</b> the "
                  "messages should go to (a private channel for the tech team is a good choice).",
                  "Click <b>Copy Webhook URL</b>."),
            ui.callout("Treat the address like a password",
                       f"Anyone who has it can post in that channel. It is saved in {vault.where()}, not in a "
                       "file. If it leaks, delete the webhook in Discord and make a new one.")])
        self.url = secret_field("https://discord.com/api/webhooks/...")
        self.add_step("Connect", "Paste the webhook address", [self.url, self.test_row()], check=self.check)
        self.ready()

    def secrets(self):
        return {"discord_url": self.url.text().strip()}

    def problem(self):
        text = self.url.text().strip()
        return "" if text.startswith("https://") and "/api/webhooks/" in text else \
            "Paste the address from Copy Webhook URL. It starts with https://discord.com/api/webhooks/"


class SlackWizard(NotifyWizard):
    channel = "slack"

    def __init__(self, parent, store, vault):
        super().__init__(parent, store, vault)
        self.add_step("Make a webhook", "Make an incoming webhook in Slack", [
            ui.rich("Messages arrive in a channel of your Slack workspace. Slack asks you to make a small "
                    "<b>app</b> of your own that is allowed to post there. It is free and takes a few minutes."),
            steps(f"Open {link('https://api.slack.com/apps')} and click <b>Create New App</b>, then <b>From "
                  "scratch</b>.",
                  "Name it <b>Stream Scheduler</b>, choose your workspace, and click <b>Create App</b>.",
                  "At the left, open <b>Incoming Webhooks</b> and switch <b>Activate Incoming Webhooks</b> on.",
                  "Click <b>Add New Webhook to Workspace</b>, choose the <b>channel</b> for the messages, and "
                  "click <b>Allow</b>.",
                  "Copy the <b>Webhook URL</b> that now shows in the list."),
            ui.callout("Not allowed to install apps?", "Some workspaces let only their admins add apps. Ask "
                       "an admin to do these steps, or to approve the app when Slack asks.", "warn", "warn"),
            ui.callout("Treat the address like a password",
                       f"Anyone who has it can post in that channel. It is saved in {vault.where()}, not in a "
                       "file. If it leaks, remove the webhook on the same Slack page.")])
        self.url = secret_field("https://hooks.slack.com/services/...")
        self.add_step("Connect", "Paste the webhook address", [self.url, self.test_row()], check=self.check)
        self.ready()

    def secrets(self):
        return {"slack_url": self.url.text().strip()}

    def problem(self):
        return "" if self.url.text().strip().startswith("https://hooks.slack.com/") else \
            "Paste the Webhook URL. It starts with https://hooks.slack.com/"


class PushoverWizard(NotifyWizard):
    channel = "pushover"

    def __init__(self, parent, store, vault):
        super().__init__(parent, store, vault)
        self.add_step("Get Pushover", "Get Pushover on your phone", [
            ui.rich("Pushover sends notifications to your phone, with a sound, also when the phone is locked. "
                    "A stream that failed arrives as a <b>high-priority</b> notification."),
            steps(f"Create an account at {link('https://pushover.net/signup')}.",
                  "Install the <b>Pushover</b> app on your phone (iPhone or Android) and log in. After a free "
                  "trial, Pushover asks for a small one-time payment per kind of phone.",
                  f"Open {link('https://pushover.net')} in a browser. Your <b>User Key</b> is at the top right "
                  "of the page. You paste it in step 3."),
            ui.callout("More than one person?",
                       "In Pushover, make a <b>Delivery Group</b> with everyone's user keys, and paste the "
                       "group's key instead of your own. Then all of them are told.")])
        self.add_step("Make a token", "Make an API token for the app", [
            steps(f"Open {link('https://pushover.net/apps/build')}.",
                  "Name: <b>Stream Scheduler</b>. The other boxes can stay empty. Tick the agreement and click "
                  "<b>Create Application</b>.",
                  "Copy the <b>API Token/Key</b> the next page shows."),
            ui.callout("Two keys, both kept safe",
                       f"The user key says who is told; the API token says who is telling. Both are saved in "
                       f"{vault.where()}, not in a file.")])
        self.user = secret_field("User Key (or a Delivery Group's key), 30 letters and digits")
        self.token = secret_field("API Token/Key, 30 letters and digits")
        self.add_step("Connect", "Paste the two keys", [
            field_grid([("User key", self.user), ("API token", self.token)]), self.test_row()], check=self.check)
        self.ready()

    def secrets(self):
        return {"pushover_user": self.user.text().strip(), "pushover_token": self.token.text().strip()}

    def problem(self):
        good = lambda t: len(t) == 30 and t.isalnum()
        return "" if good(self.user.text().strip()) and good(self.token.text().strip()) else \
            "Each key is 30 letters and digits. Paste the User Key and the API Token/Key."


class EmailWizard(NotifyWizard):
    channel = "email"
    # provider -> (server, port, security)
    PROVIDERS = [("Gmail", "smtp.gmail.com", 587, "starttls"), ("Yahoo Mail", "smtp.mail.yahoo.com", 465, "ssl"),
                 ("iCloud Mail", "smtp.mail.me.com", 587, "starttls"), ("Another provider", "", 587, "starttls")]

    def __init__(self, parent, store, vault):
        super().__init__(parent, store, vault)
        self.add_step("What you need", "Send email from an address of yours", [
            ui.rich("The app sends its messages itself, from this computer, through the mail server of an "
                    "email address you choose. For that it needs that address's <b>outgoing mail server "
                    "(SMTP)</b> and a password."),
            ui.rich("Most providers do not accept your normal password here. They give you an <b>app "
                    "password</b>: a separate password for one program, which you can cancel at any time."),
            steps(f"<b>Gmail</b>: switch on 2-Step Verification, then make an app password at "
                  f"{link('https://myaccount.google.com/apppasswords')} (name it Stream Scheduler).",
                  f"<b>Yahoo Mail</b>: {link('https://login.yahoo.com/account/security')} → <b>Generate app "
                  "password</b>.",
                  f"<b>iCloud Mail</b>: {link('https://account.apple.com')} → <b>Sign-In and Security → "
                  "App-Specific Passwords</b>.",
                  "<b>Another provider or your own mail server</b>: look for its <b>SMTP</b> settings (server, "
                  "port, and whether it uses SSL or STARTTLS). Outlook.com and Microsoft 365 often refuse this "
                  "kind of sign-in; use another address if they do."),
            ui.callout("A separate address is a good idea",
                       "For example a free mailbox made for this, sending to the people who need to know. The "
                       f"password is saved in {vault.where()}, not in a file, and the connection to the mail "
                       "server is always encrypted.")])
        self.provider = QComboBox()
        for name, *_ in self.PROVIDERS:
            self.provider.addItem(name)
        self.host = QLineEdit(self.old.get("host", ""))
        self.host.setPlaceholderText("smtp.example.org")
        self.port = QLineEdit(str(self.old.get("port", 587)))
        self.port.setFixedWidth(90)
        self.security = QComboBox()
        for key, text in (("starttls", "STARTTLS (port 587)"), ("ssl", "SSL/TLS (port 465)")):
            self.security.addItem(text, key)
        self.security.setCurrentIndex(max(0, self.security.findData(self.old.get("security", "starttls"))))
        self.user = QLineEdit(self.old.get("user", ""))
        self.user.setPlaceholderText("The address the messages come from, e.g. streams@example.org")
        self.password = secret_field("App password")
        self.to = QLineEdit(self.old.get("to", ""))
        self.to.setPlaceholderText("Who is told. Several addresses: separate them with commas.")
        known = next((i for i, p in enumerate(self.PROVIDERS) if p[1] == self.old.get("host")), None)
        self.provider.setCurrentIndex(known if known is not None else (len(self.PROVIDERS) - 1 if self.old else 0))
        self.provider.currentIndexChanged.connect(self.preset)
        if not self.old:
            self.preset(0)
        self.add_step("Connect", "Fill in the mail settings", [
            field_grid([("Provider", self.provider), ("Mail server", self.host), ("Port", self.port),
                        ("Encryption", self.security), ("Email address", self.user), ("Password", self.password),
                        ("Send to", self.to)]),
            self.test_row()], check=self.check)
        self.ready()

    def preset(self, index):
        _, host, port, security = self.PROVIDERS[index]
        if host:
            self.host.setText(host)
            self.port.setText(str(port))
            self.security.setCurrentIndex(self.security.findData(security))

    def secrets(self):
        return {"email_password": self.password.text().strip()}

    def config(self):
        return {"host": self.host.text().strip(), "port": int(self.port.text().strip() or 0),
                "security": self.security.currentData(), "user": self.user.text().strip(),
                "sender": self.user.text().strip(), "to": self.to.text().strip()}

    def problem(self):
        if not self.host.text().strip() or not self.port.text().strip().isdigit():
            return "Fill in the mail server and its port."
        if "@" not in self.user.text() or not self.password.text().strip():
            return "Fill in the email address and its password."
        if "@" not in self.to.text():
            return "Fill in who the messages are sent to."
        return ""


NOTIFY_WIZARDS = {"email": EmailWizard, "discord": DiscordWizard, "slack": SlackWizard, "pushover": PushoverWizard}
