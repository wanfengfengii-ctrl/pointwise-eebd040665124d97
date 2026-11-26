import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from switch_flow import SwitchFlow
from tests.support import ProcessDesk, WorkbenchCase


class TestSwitch(WorkbenchCase):
    desk_class = ProcessDesk

    def test_browser_switch_handoff(self):
        flow = SwitchFlow(Path(self.root), desk_class=self.desk_class)
        # WorkbenchCase also tracks desks created through self.desk(); keep the
        # flow's process cleanup under the test case's cleanup policy.
        original_desk = flow.desk

        def tracked_desk(role):
            desk = original_desk(role)
            self.desks[role] = desk
            return desk

        flow.desk = tracked_desk
        self.addCleanup(flow.close)
        result = flow.run()
        self.assertEqual(result['frame_at_1000ms']['A']['index'], 2)
        self.assertEqual(result['frame_at_1000ms']['B']['index'], 1)
        self.assertEqual(result['east_report']['started'], 2)
        self.assertEqual(result['east_report']['finished'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
