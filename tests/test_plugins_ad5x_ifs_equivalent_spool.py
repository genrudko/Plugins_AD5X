from __future__ import annotations
import importlib.util, pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
P = ROOT / 'moonraker' / 'components' / 'plugins_ad5x_ifs_model.py'
spec = importlib.util.spec_from_file_location('ifs_equivalent_model', P)
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
spec.loader.exec_module(model)

def slots():
    return [{'slot': 1, 'present': True}, {'slot': 2, 'present': True}, {'slot': 3, 'present': True}, {'slot': 4, 'present': False}]

def meta(source_material='PLA'):

    def z(m, c):
        return {'zmod_compat': {'material': m, 'color': c}}
    return {'slots': {1: z(source_material, '#AA0000'), 2: {**z('PLA', '#AA0000'), 'material': 'PETG', 'color': '#FFFFFF'}, 3: z('PETG', '#AA0000'), 4: z('PLA', '#AA0000')}}

class EquivalentSpoolPreviewTests(unittest.TestCase):

    def test_exact_provider_identity_and_presence_match_in_provider_slot_order(self):
        result = model.build_equivalent_spool_preview(slots(), 1, meta(), ['PLA', 'PETG', 'TPU'])
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['eligible_slots'], [2])
        self.assertEqual(result['next_slot'], 2)
        self.assertFalse(result['automatic_transition_enabled'])
        self.assertFalse(result['transition_hardware_accepted'])
        self.assertEqual(result['matching']['priority'], 'ascending_physical_slot')
        by_slot = {x['slot']: x for x in result['candidates']}
        self.assertTrue(by_slot[2]['eligible'])
        self.assertIn('material_mismatch', by_slot[3]['blockers'])
        self.assertIn('slot_empty', by_slot[4]['blockers'])
        self.assertEqual(by_slot[2]['material'], 'PLA')

    def test_manual_overlay_cannot_create_provider_equivalence(self):
        data = meta()
        data['slots'][2]['material'] = 'ABS'
        data['slots'][2]['color'] = '#00FF00'
        result = model.build_equivalent_spool_preview(slots(), 1, data, ['PLA', 'PETG'])
        self.assertEqual(result['eligible_slots'], [2])

    def test_provider_source_material_normalization_matches_analog_prutok(self):
        result = model.build_equivalent_spool_preview(slots(), 1, meta('UNKNOWN'), ['PLA', 'PETG'])
        self.assertEqual(result['source']['effective_material'], 'PLA')
        self.assertTrue(result['source']['material_normalized_to_pla'])
        self.assertEqual(result['next_slot'], 2)

    def test_missing_provider_identity_or_unsupported_mode_fails_closed(self):
        unknown = model.build_equivalent_spool_preview(slots(), 1, meta(), [], 'display_off')
        self.assertEqual(unknown['status'], 'unknown')
        self.assertEqual(unknown['eligible_slots'], [])
        suspended = model.build_equivalent_spool_preview(slots(), 1, meta(), ['PLA'], 'native_display')
        self.assertEqual(suspended['status'], 'suspended')
        self.assertFalse(suspended['automatic_transition_enabled'])

    def test_normalized_module_exposes_preview_but_not_endless_transition(self):
        raw = {'available': True, 'state': 'ready', 'active_slot': 1, 'provider_mode': 'display_off', 'provider_material_types': ['PLA', 'PETG'], 'slots': slots()}
        module = model.normalize_module(raw, meta(), 'standby', True, {'state': 'idle', 'action': '', 'slot': 0, 'error': ''})
        self.assertEqual(module['equivalent_spool']['eligible_slots'], [2])
        self.assertTrue(module['capabilities']['mapping']['equivalent_spool_preview'])
        self.assertFalse(module['capabilities']['mapping']['endless_spool'])
if __name__ == '__main__':
    unittest.main()
