"""Backtest harness for the Disease Outflow Forecaster.

Compares the SEIR + mobility + Monte Carlo simulator against archived JHU CSSE
COVID-19 case counts to produce a measured 95% prediction-interval coverage
number. Replaces the placeholder coverage value in ``app.simulate.run``'s
calibration block.
"""
