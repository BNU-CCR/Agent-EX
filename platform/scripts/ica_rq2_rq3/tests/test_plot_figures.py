"""UNIT-only plotting arithmetic: no figure files or experimental observations."""
import importlib.util
from pathlib import Path
import unittest
import pandas as pd
import numpy as np

SCRIPT=Path(__file__).resolve().parents[1]/'plot_figures.py'
spec=importlib.util.spec_from_file_location('ica_plots',SCRIPT)
plots=importlib.util.module_from_spec(spec)
spec.loader.exec_module(plots)


class PlotArithmeticTests(unittest.TestCase):
    def test_long_panel_never_mixes_overlapping_t30_prefixes(self):
        frame=pd.DataFrame([dict(horizon=30,value=100),dict(horizon=60,value=2)])
        self.assertEqual(plots.long_panel(frame).value.tolist(),[2])

    def test_seed_points_equal_identity_before_seed_mean(self):
        frame=pd.DataFrame([dict(matched_seed=1,network_b='B1',value=1),
                            dict(matched_seed=1,network_b='B1',value=3),
                            dict(matched_seed=2,network_b='B1',value=8),
                            dict(matched_seed=2,network_b='B1',value=10)])
        fig,ax=plots.plt.subplots()
        try:
            plots.seed_points(ax,frame,'network_b','value',['B1'])
            self.assertTrue(np.allclose(ax.collections[0].get_offsets()[:,1],[2,9]))
            self.assertTrue(np.allclose(ax.lines[-1].get_ydata(),[5.5,5.5]))
        finally:plots.plt.close(fig)

    def test_empty_opportunities_stay_missing(self):
        frame=pd.DataFrame([dict(matched_seed=1,network_b='B1',value=np.nan)])
        fig,ax=plots.plt.subplots()
        try:
            plots.seed_points(ax,frame,'network_b','value',['B1'])
            self.assertEqual(len(ax.collections[0].get_offsets()),0)
        finally:plots.plt.close(fig)


if __name__=='__main__':unittest.main()
