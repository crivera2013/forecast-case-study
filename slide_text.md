# NYC Pothole Complaints Forecast — Presentation Deck

Executive decision briefing for NYC Department of Transportation leadership.

---

## Slide 1: Executive Summary
**NYC Pothole Complaints Forecast**

- **What this report is:** A 9-month predictive forecast of monthly NYC 311 pothole complaints (Aug 2026 – Apr 2027) modeled from 200 months of historical data (991,071 complaints; Dec 2009 – Jul 2026).
- **Goal:** To forecast the number of pothole complaints so that NYC Department of Transportation (DOT) can plan ahead to meet the demand. With significantly increased snowfall in 2026, pothole occurances will increase this year and DOT must be prepared to meet the moment.
**Key Volume Targets:**
- **Immediate Volume (Aug '26)**: 2,758 projected complaints (Baseline summer volume; ~2.8k/mo).
- **Projected Peak (Mar '27)**: 10,810 projected complaints (+270% annual freeze-thaw surge over baseline).
- **Historical Weather Spike**: 25,171 complaints (March 2026 5.1× baseline weather anomaly).
---

## Slide 2: 9-Month Complaints Forecast (Aug 2026 – Apr 2027)

**Complaints Forecast & Confidence Bounds**

Complaints remain at baseline through autumn (~2.2k–2.8k/mo), then surge to 10.8k in late winter. 2 forecasting models and the 2015 complaint history are shown to provide leadership with insight over how many complaints there will probably be.

| Month | Primary Forecast (B Multiplicative) | Event-Aware Alt (A Additive) | 2015 Post-Snow Benchmark | Seasonal Pattern |
|---|---|---|---|---|
| **Aug 2026** | **2,758** | 3,067 | **5,459** | Summer baseline (~2.8k) |
| **Sep 2026** | **2,369** | 2,750 | **3,953** | Summer trough (~2.4k) |
| **Oct 2026** | **2,571** | 2,809 | **3,893** | Autumn baseline (~2.6k) |
| **Nov 2026** | **2,169** | 2,431 | **3,019** | Pre-winter low (~2.2k) |
| **Dec 2026** | **3,004** | 3,377 | **4,295** | Winter onset (~3.0k) |
| **Jan 2027** | **3,947** | 4,178 | **4,818** | Winter surge ramp (~3.9k) |
| **Feb 2027** | **5,119** | 5,714 | **7,571** | Late winter ramp (~5.1k) |
| **Mar 2027** | **10,810** | 11,326 | **9,227** | **ANNUAL PEAK (10.8k; +270%)** |
| **Apr 2027** | **5,823** | 6,880 | **6,748** | Spring thaw (~5.8k) |
**Operational Advisory for Leadership:** Due to unusually heavy snowfall in NYC this year, actual complaint volumes over the next ~3–4 months (Aug–Nov 2026) are likely to track higher than the baseline model prediction. Operations should plan capacity toward the upper forecast range or the Event-Aware alternate model.

## Slide 3: 200-Month Baseline (2009–2026)

**Historical Baseline & Weather Shocks**

- **Total Volume**: 991,071 complaints across 200 months (average: ~4,955/mo).
- **2015 Snowstorms**: Severe winter blizzards drove a sustained ~20% baseline increase.
- **March 2026 Spike**: Record 25,171 complaints (5.1× normal volume weather anomaly).

---

## Slide 4: Seasonal Multipliers

**Freeze-Thaw Cyclicity**

- **March Peak (+148%)**: Annual peak in all 16 years. Rapid freeze-thaw cycles around 32°F (0°C) maximize hydraulic asphalt ruptures.
- **November Low (-36%)**: Annual low. Dry, stable autumn temperatures minimize new road surface damage.
- **Proportional Scaling**: Surges compound baseline volume (+50% to +150%) rather than adding fixed counts.

---

## Slide 5: Model Selection & Empirical Validation

**Evaluation of 28 Prophet Configurations**

| Model Configuration | Strategy | Val 1 (2023-24) | Val 2 (2024-25) | Avg Val MAPE | 14-Fold CV | Held-Out Test |
|---|---|---|---|---|---|---|
| **B (multiplicative) \| cp=none** 🏆 | None | **6.0%** | **16.8%** | **11.4%** | **21.7%** | 33.9% |
| B (multiplicative) \| cp=auto | Auto | 14.7% | 9.6% | 12.2% | 19.7% | 32.4% |
| B (multiplicative) \| cp=events | Events | 13.1% | 11.6% | 12.4% | 18.7% | 27.2% |
| B (multiplicative) \| cp=regressors | Regressors | 13.5% | 11.4% | 12.5% | 31.3% | 28.2% |
| B (multiplicative) \| cp=auto-flexible+regressors | Flex+Reg | 17.9% | 11.5% | 14.7% | 32.2% | 24.4% |
| B (multiplicative) \| cp=events+regressors | Events+Reg | 16.6% | 13.0% | 14.8% | 31.6% | 24.5% |
| A (additive-smooth) \| cp=events | Events | 16.3% | 13.4% | 14.9% | 25.9% | 33.5% |
| A (additive-smooth) \| cp=auto-flexible | Flex | 17.7% | 13.5% | 15.6% | 26.5% | 33.5% |

*Metric Definition: **MAPE (Mean Absolute Percentage Error)** $= \frac{1}{n}\sum |\frac{y - \hat{y}}{y}| \times 100\%$. Measures average forecast error as a percentage of actuals (11.4% = 88.6% accuracy).

---

## Slide 6: Outlier Stress-Testing

**March 2026 Weather Anomaly**

- **Actual**: 25,171 (5.1× baseline)
- **Predicted**: 7,036
- **Error**: 18,135 (72.0% APE)
- **Test MAPE**: 33.9% with outlier, **30.4%** without outlier.
- **Decision**: Retaining genuine climate anomalies keeps baseline models calibrated without hiding risk.

---

## Slide 7: Methodology & Specifications

**Model Formulation & Pipeline**

- **Data**: NYC 311 Socrata API (`Street Condition` / `Pothole`). 200 full months (Dec 2009 – Jul 2026).
- **Model**: Linear growth, multiplicative yearly seasonality: $y(t) = g(t) \times (1 + s(t)) + \varepsilon_t$.
- **Priors**: `changepoint_prior_scale=0.01`, `seasonality_prior_scale=100.0`, 300 MCMC samples (95% CI).
- **Validation**: 2 rolling windows (6.0% and 16.8% MAPE) + 14-fold cross-validation (21.7% MAPE).

---

## Slide 8: Roadmap & Limitations

**Next Steps**

- **Weather Regressors**: NOAA freeze-thaw, snow, and precipitation feeds.
- **Borough Disaggregation**: Spatial breakdowns for localized crew dispatch.
- **Budget Linkage**: Translate complaints directly to asphalt tonnage and labor hours.
- **Automation**: Automated monthly retraining via GitHub Actions upon 311 updates.
