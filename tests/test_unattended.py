"""Tests of the Unattended PC settings (winsetup.py) that can run on any system: the tasks' XML, when the
lock locks, when the computer is woken, and what the administrator part decides. Windows itself (Task
Scheduler, the LSA secret, UAC) is replaced by stand-ins. Run: python -m unittest discover tests"""
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import winsetup

import test_core as core

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def parse(xml):
    return ET.fromstring(xml.split("\n", 1)[1])   # without the declaration, which names UTF-16


class TaskXmlTest(unittest.TestCase):
    def test_lock_task(self):
        task = parse(winsetup.lock_task_xml("CHURCH-PC\\Streaming"))
        self.assertEqual(task.find("t:Triggers/t:LogonTrigger/t:UserId", NS).text, "CHURCH-PC\\Streaming")
        self.assertEqual(task.find("t:Principals/t:Principal/t:LogonType", NS).text, "InteractiveToken")
        self.assertEqual(task.find("t:Principals/t:Principal/t:RunLevel", NS).text, "LeastPrivilege")
        self.assertIn("--lock-after-boot", task.find("t:Actions/t:Exec/t:Arguments", NS).text)
        self.assertEqual(task.find("t:Settings/t:WakeToRun", NS).text, "false")

    def test_wake_task(self):
        times = [datetime(2027, 11, 13, 8, 55), datetime(2027, 11, 14, 6, 55)]
        task = parse(winsetup.wake_task_xml("Streaming & Co <test>", times))
        self.assertEqual([t.text for t in task.findall("t:Triggers/t:TimeTrigger/t:StartBoundary", NS)],
                         ["2027-11-13T08:55:00", "2027-11-14T06:55:00"])
        self.assertEqual(task.find("t:Settings/t:WakeToRun", NS).text, "true")
        self.assertEqual(task.find("t:Settings/t:DisallowStartIfOnBatteries", NS).text, "false")
        self.assertEqual(task.find("t:Principals/t:Principal/t:UserId", NS).text, "Streaming & Co <test>")
        self.assertIn("--run", task.find("t:Actions/t:Exec/t:Arguments", NS).text)


class LockTest(unittest.TestCase):
    def test_locks_only_just_after_start(self):
        locked = []
        self.assertTrue(winsetup.lock_after_boot(timedelta(seconds=40), lambda: locked.append(1)))
        self.assertFalse(winsetup.lock_after_boot(timedelta(minutes=10), lambda: locked.append(1)))
        self.assertEqual(locked, [1])

    def test_lock_task_asks_for_administrator_only_when_refused(self):
        made, asked = [], []
        real = winsetup.create_task
        self.addCleanup(setattr, winsetup, "create_task", real)
        winsetup.create_task = lambda name, xml: made.append(name)
        winsetup.set_lock_task(True, "PC\\Streaming", elevate=lambda args: asked.append(args) or winsetup.DONE)
        self.assertEqual((made, asked), ([winsetup.LOCK_TASK], []))

        def refused(name, xml):
            raise winsetup.WinSetupError("Access is denied.")
        winsetup.create_task = refused
        winsetup.set_lock_task(True, "PC\\Streaming", elevate=lambda args: asked.append(args) or winsetup.DONE)
        self.assertEqual(asked, [["lock-task", "--account", "PC\\Streaming"]])
        with self.assertRaises(winsetup.WinSetupError):
            winsetup.set_lock_task(True, "PC\\Streaming", elevate=lambda args: winsetup.CANCELLED)


class WakeTest(core.Base):
    SAT = datetime(2027, 11, 12, 12, 0)   # Friday noon: Sunday's stream is created Saturday 9:00

    def setUp(self):
        super().setUp()
        self.store.schedules[0]["destinations"] = ["yt"]
        self.store.encoders.append({"id": "e1", "kind": "obs", "name": "PC", "host": "127.0.0.1", "port": 4455,
                                    "local": True, "auth": False})
        self.made, self.deleted = [], []
        self.create = lambda name, xml: self.made.append(xml)
        self.delete = lambda name: self.deleted.append(name)

    def test_times_before_creating_and_before_obs(self):
        self.assertEqual(winsetup.wake_times(self.store, self.SAT)[:2],
                         [datetime(2027, 11, 13, 8, 55), datetime(2027, 11, 20, 8, 55)])
        self.store.schedules[0].update(encoder_id="e1")   # opened 60 and checked 55 minutes before 8:00
        self.assertEqual(winsetup.wake_times(self.store, self.SAT)[:2],
                         [datetime(2027, 11, 13, 8, 55), datetime(2027, 11, 14, 6, 55)])
        self.store.schedules[0].update(obs_open=0)
        self.assertEqual(winsetup.wake_times(self.store, self.SAT)[1], datetime(2027, 11, 14, 7, 0))
        self.assertTrue(all(t - self.SAT <= winsetup.WAKE_AHEAD for t in winsetup.wake_times(self.store, self.SAT)))
        self.store.schedules[0]["overrides"]["2027-11-14"] = {"skip": True}
        self.assertNotIn(datetime(2027, 11, 13, 8, 55), winsetup.wake_times(self.store, self.SAT))

    def test_task_rewritten_only_when_times_change(self):
        sync = lambda now: winsetup.sync_wake(self.store, now, self.create, self.delete)
        self.assertEqual(sync(self.SAT), "")
        self.assertEqual(self.made, [])                     # off by default
        self.store.settings["wake_before_stream"] = True
        sync(self.SAT)
        sync(self.SAT + timedelta(minutes=1))
        self.assertEqual(len(self.made), 1)
        sync(datetime(2027, 11, 13, 9, 30))                 # Saturday's time has passed: rewritten
        self.assertEqual(len(self.made), 2)
        self.store.settings["wake_before_stream"] = False
        sync(self.SAT)
        self.assertEqual(self.deleted, [winsetup.WAKE_TASK])
        self.assertNotIn("wake_written", self.store.settings)

    def test_a_refused_task_is_said(self):
        self.store.settings["wake_before_stream"] = True

        def refused(name, xml):
            raise winsetup.WinSetupError("Access is denied.")
        self.assertEqual(winsetup.sync_wake(self.store, self.SAT, refused, self.delete), "Access is denied.")
        self.assertEqual(self.store.settings["wake_error"], "Access is denied.")


class ElevatedTest(unittest.TestCase):
    """What the administrator copy decides, with Windows replaced."""

    def setUp(self):
        self.done = []
        fakes = {"is_admin_account": lambda d, u: u == "Admin",
                 "_ask_password": lambda d, u: None if u == "Shy" else "pw",
                 "set_autologon": lambda d, u, p: self.done.append(("on", d, u, p)),
                 "clear_autologon": lambda: self.done.append(("off",)),
                 "create_task": lambda name, xml: self.done.append(("task", name)),
                 "_message": lambda title, text: self.done.append(("said", text))}
        for name, fake in fakes.items():
            real = getattr(winsetup, name)
            setattr(winsetup, name, fake)
            self.addCleanup(setattr, winsetup, name, real)

    def run_it(self, *args):
        return winsetup.elevated_main(["app.py", "--elevated", *args])

    def test_turns_on_for_a_standard_account(self):
        self.assertEqual(self.run_it("autologon-on", "--domain", "PC", "--user", "Streaming"), winsetup.DONE)
        self.assertEqual(self.done, [("on", "PC", "Streaming", "pw")])

    def test_refuses_an_administrator_and_a_cancelled_password(self):
        self.assertEqual(self.run_it("autologon-on", "--domain", "PC", "--user", "Admin"), winsetup.REFUSED_ADMIN)
        self.assertEqual(self.run_it("autologon-on", "--domain", "PC", "--user", "Shy"), winsetup.CANCELLED)
        self.assertFalse([d for d in self.done if d[0] == "on"])

    def test_off_lock_task_and_unknown(self):
        self.assertEqual(self.run_it("autologon-off"), winsetup.DONE)
        self.assertEqual(self.run_it("lock-task", "--account", "PC\\Streaming"), winsetup.DONE)
        self.assertEqual(self.run_it("something-else"), winsetup.FAILED)
        self.assertEqual(self.done, [("off",), ("task", winsetup.LOCK_TASK)])

    def test_a_windows_error_is_said_and_fails(self):
        def broken(d, u, p):
            raise OSError("Access is denied")
        winsetup.set_autologon = broken
        self.assertEqual(self.run_it("autologon-on", "--domain", "PC", "--user", "Streaming"), winsetup.FAILED)
        self.assertIn("Access is denied", self.done[-1][1])


if __name__ == "__main__":
    unittest.main()
