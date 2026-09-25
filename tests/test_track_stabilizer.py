import unittest
from core.video_annotator import SpatialTrackStabilizer

class TestTrackStabilizer(unittest.TestCase):
    def test_relinking_dropped_tracks(self):
        stabilizer = SpatialTrackStabilizer(max_missing_frames=45, match_dist_ratio=0.20)
        
        # Frame 1 to 20: Person at center (300, 100, 380, 350), raw_id 1
        for f in range(1, 21):
            c_id = stabilizer.update(raw_id=1, bbox=(300, 100, 380, 350), frame_idx=f, frame_w=640, frame_h=480)
            self.assertEqual(c_id, 1)

        # Frame 21 to 30: Occlusion / disappeared (no detections)

        # Frame 31: Person reappears at same location (305, 102, 385, 352), but ByteTrack gives raw_id 76
        c_id_relink = stabilizer.update(raw_id=76, bbox=(305, 102, 385, 352), frame_idx=31, frame_w=640, frame_h=480)
        
        # It must be linked back to canonical ID 1, not 76!
        self.assertEqual(c_id_relink, 1)

    def test_phantom_pruning_and_roles(self):
        stabilizer = SpatialTrackStabilizer()

        # Adult 1: 50 frames, height 300px
        for f in range(1, 51):
            stabilizer.update(raw_id=1, bbox=(100, 50, 180, 350), frame_idx=f, frame_w=640, frame_h=480)

        # Child: 40 frames, height 120px (less than half adult height)
        for f in range(1, 41):
            stabilizer.update(raw_id=2, bbox=(250, 200, 310, 320), frame_idx=f, frame_w=640, frame_h=480)

        # Phantom noise: only 3 frames
        for f in range(1, 4):
            stabilizer.update(raw_id=99, bbox=(500, 50, 520, 80), frame_idx=f, frame_w=640, frame_h=480)

        stabilizer.finalize_roles(frame_h=480)

        # Phantom track 99 should have count 3 < 15
        self.assertLess(stabilizer.canonical_counts[3], 15)

        # Roles
        self.assertEqual(stabilizer.get_role(1), "Người lớn")
        self.assertEqual(stabilizer.get_role(2), "Trẻ nhỏ / Em bé")

if __name__ == "__main__":
    unittest.main()
