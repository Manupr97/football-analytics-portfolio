import matplotlib
matplotlib.use('Agg')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import os
from scipy import stats

# ─── Paths ───────────────────────────────────────────────────────────────────
DATA_PATH   = "C:/Users/manue/OneDrive/Escritorio/portfolio/player-similarity-model/data/features/features_base_mvp.parquet"
OUTPUT_DIR  = "C:/Users/manue/OneDrive/Escritorio/portfolio/player-similarity-model/data/features/audit/"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── 1. Load & inspect ───────────────────────────────────────────────────────
df = pd.read_parquet(DATA_PATH)
print("=" * 70)
print("STEP 1 – DATASET OVERVIEW")
print("=" * 70)
print(f"Shape: {df.shape}")
print(f"\nAll columns ({len(df.columns)}):")
for col in df.columns:
    print(f"  {col:45s}  {str(df[col].dtype)}")

# ─── 2. Identify ID vs feature columns ──────────────────────────────────────
ID_COLS = ['jugador', 'equipo', 'competicion', 'posicion', 'season']
id_cols_present    = [c for c in ID_COLS if c in df.columns]
feature_cols       = [c for c in df.columns if c not in id_cols_present and pd.api.types.is_numeric_dtype(df[c])]
non_numeric_extra  = [c for c in df.columns if c not in id_cols_present and not pd.api.types.is_numeric_dtype(df[c])]

print("\n" + "=" * 70)
print("STEP 2 – COLUMN CLASSIFICATION")
print("=" * 70)
print(f"ID columns present    : {id_cols_present}")
print(f"Extra non-numeric cols: {non_numeric_extra}")
print(f"Feature columns ({len(feature_cols)}): {feature_cols}")

# ─── 3. Descriptive stats ────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3 – DESCRIPTIVE STATISTICS")
print("=" * 70)
desc_rows = []
for col in feature_cols:
    s = df[col].dropna()
    desc_rows.append({
        'feature'  : col,
        'mean'     : s.mean(),
        'std'      : s.std(),
        'min'      : s.min(),
        'p25'      : s.quantile(0.25),
        'p75'      : s.quantile(0.75),
        'max'      : s.max(),
        'skewness' : stats.skew(s),
        'kurtosis' : stats.kurtosis(s),
        'n_valid'  : len(s),
        'n_null'   : df[col].isna().sum(),
    })
audit_stats = pd.DataFrame(desc_rows)
out_stats = os.path.join(OUTPUT_DIR, "audit_stats.csv")
audit_stats.to_csv(out_stats, index=False)
print(audit_stats.to_string(index=False))
print(f"\nSaved: {out_stats}")

# ─── 4. Correlation matrix ───────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 4 – CORRELATION MATRIX")
print("=" * 70)
corr = df[feature_cols].corr()
out_corr = os.path.join(OUTPUT_DIR, "audit_correlations.csv")
corr.to_csv(out_corr)
print(f"Saved: {out_corr}")

# ─── 5. High-correlation pairs |r| > 0.8 ────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 5 – HIGH-CORRELATION PAIRS  |r| > 0.8")
print("=" * 70)
high_corr_pairs = []
for i in range(len(feature_cols)):
    for j in range(i + 1, len(feature_cols)):
        r = corr.iloc[i, j]
        if abs(r) > 0.8:
            high_corr_pairs.append({
                'feature_A': feature_cols[i],
                'feature_B': feature_cols[j],
                'r'        : round(r, 4),
                'abs_r'    : round(abs(r), 4),
            })
high_corr_df = pd.DataFrame(high_corr_pairs).sort_values('abs_r', ascending=False).reset_index(drop=True)
if len(high_corr_df):
    print(high_corr_df.to_string(index=False))
else:
    print("No pairs with |r| > 0.8 found.")
out_hc = os.path.join(OUTPUT_DIR, "audit_high_correlations.csv")
high_corr_df.to_csv(out_hc, index=False)
print(f"\nSaved: {out_hc}")

# ─── 6. Near-zero variance features ─────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 6 – NEAR-ZERO VARIANCE FEATURES  (var < 0.01)")
print("=" * 70)
variances = df[feature_cols].var()
low_var = variances[variances < 0.01].sort_values()
if len(low_var):
    print(low_var.to_string())
else:
    print("No features with variance < 0.01.")

# ─── 7. Mean by competicion ──────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 7 – MEAN BY COMPETICION")
print("=" * 70)
if 'competicion' in df.columns:
    by_league = df.groupby('competicion')[feature_cols].mean()
    out_bl = os.path.join(OUTPUT_DIR, "audit_by_league.csv")
    by_league.to_csv(out_bl)
    print(by_league.T.to_string())
    print(f"\nSaved: {out_bl}")
else:
    print("Column 'competicion' not found.")

# ─── 8. Counts by posicion ───────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 8 – COUNTS BY POSICION")
print("=" * 70)
if 'posicion' in df.columns:
    pos_counts = df['posicion'].value_counts()
    pos_pct    = (pos_counts / len(df) * 100).round(2)
    pos_df     = pd.DataFrame({'count': pos_counts, 'pct': pos_pct})
    print(pos_df.to_string())
else:
    print("Column 'posicion' not found.")

# ─── 9a. Heatmap correlations ────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 9 – GENERATING PLOTS")
print("=" * 70)

fig, ax = plt.subplots(figsize=(20, 18))
sns.heatmap(corr, ax=ax, annot=False, cmap='coolwarm', center=0,
            xticklabels=True, yticklabels=True)
ax.set_title("Feature Correlation Heatmap", fontsize=16, fontweight='bold')
plt.tight_layout()
out_hm = os.path.join(OUTPUT_DIR, "heatmap_correlations.png")
fig.savefig(out_hm, dpi=150)
plt.close(fig)
print(f"Saved: {out_hm}")

# ─── 9b. Volume features (_p90) ─────────────────────────────────────────────
vol_cols = [c for c in feature_cols if c.endswith('_p90')]
print(f"\nVolume (_p90) columns ({len(vol_cols)}): {vol_cols}")
if vol_cols:
    ncols = 4
    nrows = int(np.ceil(len(vol_cols) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(20, 12))
    axes = axes.flatten()
    for i, col in enumerate(vol_cols):
        axes[i].hist(df[col].dropna(), bins=30, edgecolor='white', color='steelblue')
        axes[i].set_title(col, fontsize=9)
        axes[i].set_xlabel('')
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    fig.suptitle("Distribution of Volume Features (_p90)", fontsize=14, fontweight='bold')
    plt.tight_layout()
    out_vol = os.path.join(OUTPUT_DIR, "dist_volume_features.png")
    fig.savefig(out_vol, dpi=150)
    plt.close(fig)
    print(f"Saved: {out_vol}")
else:
    print("No _p90 columns found.")

# ─── 9c. Style features (non-p90 numerics) ───────────────────────────────────
style_cols = [c for c in feature_cols if not c.endswith('_p90')]
print(f"\nStyle columns ({len(style_cols)}): {style_cols}")
if style_cols:
    ncols = 4
    nrows = int(np.ceil(len(style_cols) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(20, 12))
    axes = axes.flatten()
    for i, col in enumerate(style_cols):
        axes[i].hist(df[col].dropna(), bins=30, edgecolor='white', color='darkorange')
        axes[i].set_title(col, fontsize=9)
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    fig.suptitle("Distribution of Style Features", fontsize=14, fontweight='bold')
    plt.tight_layout()
    out_sty = os.path.join(OUTPUT_DIR, "dist_style_features.png")
    fig.savefig(out_sty, dpi=150)
    plt.close(fig)
    print(f"Saved: {out_sty}")
else:
    print("No style columns found.")

# ─── 9d. PCA 2D ──────────────────────────────────────────────────────────────
df_feat = df[feature_cols].dropna()
df_meta = df.loc[df_feat.index]

scaler = StandardScaler()
X_scaled = scaler.fit_transform(df_feat)

pca = PCA(n_components=2, random_state=42)
X_pca = pca.fit_transform(X_scaled)
explained = pca.explained_variance_ratio_

print(f"\nPCA explained variance: PC1={explained[0]:.4f} ({explained[0]*100:.2f}%), PC2={explained[1]:.4f} ({explained[1]*100:.2f}%)")

pca_df = pd.DataFrame(X_pca, columns=['PC1', 'PC2'], index=df_feat.index)
if 'competicion' in df_meta.columns:
    pca_df['competicion'] = df_meta['competicion'].values
else:
    pca_df['competicion'] = 'unknown'

# outliers (> 2 std from centre)
center = pca_df[['PC1', 'PC2']].mean()
std_   = pca_df[['PC1', 'PC2']].std()
dist   = np.sqrt(((pca_df[['PC1', 'PC2']] - center) / std_).pow(2).sum(axis=1))
outlier_idx = dist[dist > 2].index

fig, ax = plt.subplots(figsize=(14, 10))
leagues = pca_df['competicion'].unique()
palette = sns.color_palette("tab10", len(leagues))
for idx_l, league in enumerate(sorted(leagues)):
    mask = pca_df['competicion'] == league
    ax.scatter(pca_df.loc[mask, 'PC1'], pca_df.loc[mask, 'PC2'],
               label=league, color=palette[idx_l], alpha=0.6, s=40)

# annotate outliers
if 'jugador' in df_meta.columns:
    for oi in outlier_idx:
        name = df_meta.loc[oi, 'jugador'] if oi in df_meta.index else str(oi)
        ax.annotate(name, (pca_df.loc[oi, 'PC1'], pca_df.loc[oi, 'PC2']),
                    fontsize=7, alpha=0.8)

ax.set_xlabel(f"PC1 ({explained[0]*100:.1f}% var)", fontsize=12)
ax.set_ylabel(f"PC2 ({explained[1]*100:.1f}% var)", fontsize=12)
ax.set_title("PCA 2D – coloured by competicion", fontsize=14, fontweight='bold')
ax.legend(title='League', bbox_to_anchor=(1.01, 1), loc='upper left')
plt.tight_layout()
out_pca = os.path.join(OUTPUT_DIR, "pca_2d.png")
fig.savefig(out_pca, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"Saved: {out_pca}")

# ─── 9e. Boxplot by league ───────────────────────────────────────────────────
box_cols = ['goals_p90','xg_p90','npxg_p90','shots_p90','dribbles_completed_p90']
box_cols_present = [c for c in box_cols if c in df.columns]
print(f"\nBoxplot columns present: {box_cols_present}")
if box_cols_present and 'competicion' in df.columns:
    df_melt = df[['competicion'] + box_cols_present].melt(id_vars='competicion',
                                                          var_name='metric',
                                                          value_name='value')
    fig, ax = plt.subplots(figsize=(18, 10))
    sns.boxplot(data=df_melt, x='metric', y='value', hue='competicion',
                ax=ax, palette='Set2')
    ax.set_title("Key Metrics by League", fontsize=14, fontweight='bold')
    ax.set_xlabel("Metric", fontsize=12)
    ax.set_ylabel("Value", fontsize=12)
    ax.legend(title='League', bbox_to_anchor=(1.01, 1), loc='upper left')
    plt.xticks(rotation=20)
    plt.tight_layout()
    out_box = os.path.join(OUTPUT_DIR, "boxplot_by_league.png")
    fig.savefig(out_box, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {out_box}")
else:
    print("Skipping boxplot – columns not found.")

# ─── 10. FULL SUMMARY ────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 10 – COMPLETE FINDINGS SUMMARY")
print("=" * 70)

print("\n--- HIGH-CORRELATION PAIRS (candidates for removal) ---")
if len(high_corr_df):
    for _, row in high_corr_df.iterrows():
        print(f"  |r|={row['abs_r']:.4f}  {row['feature_A']}  <-->  {row['feature_B']}")
else:
    print("  None found above |r| > 0.8 threshold.")

print("\n--- LOW VARIANCE FEATURES (var < 0.01) ---")
if len(low_var):
    for feat, v in low_var.items():
        print(f"  {feat}: var={v:.6f}")
else:
    print("  None found.")

print("\n--- LEAGUE DIFFERENCES ---")
if 'competicion' in df.columns:
    # coefficient of variation across league means
    cv_between = by_league.std() / by_league.mean().abs()
    cv_between = cv_between.sort_values(ascending=False)
    print("  Features with highest variation between leagues (CV of league means):")
    for feat, cv in cv_between.head(10).items():
        print(f"    {feat:45s}  CV={cv:.4f}")

print("\n--- PCA VARIANCE EXPLAINED ---")
print(f"  PC1: {explained[0]*100:.2f}%   PC2: {explained[1]*100:.2f}%   Total 2D: {sum(explained)*100:.2f}%")

# cumulative variance with more components
pca_full = PCA(random_state=42).fit(X_scaled)
cumvar = np.cumsum(pca_full.explained_variance_ratio_)
n80 = int(np.searchsorted(cumvar, 0.80)) + 1
n90 = int(np.searchsorted(cumvar, 0.90)) + 1
n95 = int(np.searchsorted(cumvar, 0.95)) + 1
print(f"  Components needed for 80% variance: {n80}")
print(f"  Components needed for 90% variance: {n90}")
print(f"  Components needed for 95% variance: {n95}")

print("\n--- RECOMMENDATION: USE ALL LEAGUES TOGETHER vs. NORMALIZE BY LEAGUE ---")
if 'competicion' in df.columns:
    leagues_in_data = df['competicion'].unique()
    print(f"  Leagues present: {sorted(leagues_in_data)}")
    print(f"  Number of leagues: {len(leagues_in_data)}")
    # check if between-league variance is large relative to overall
    overall_std = df[feature_cols].std()
    league_mean_std = by_league.std()  # std of league means
    ratio = (league_mean_std / overall_std).mean()
    print(f"  Mean ratio (between-league std / overall std): {ratio:.4f}")
    if ratio > 0.3:
        print("  RECOMMENDATION: Normalize by league (z-score within each league) before")
        print("  computing similarity — league-level differences are substantial.")
    else:
        print("  RECOMMENDATION: Leagues appear comparable; normalizing globally with")
        print("  StandardScaler across all leagues should be sufficient. However,")
        print("  consider normalizing by league if the model is used cross-league.")

print("\n--- DATASET SIZE ---")
print(f"  Total rows    : {len(df)}")
print(f"  Feature cols  : {len(feature_cols)}")
print(f"  Rows with any NaN in features: {df[feature_cols].isna().any(axis=1).sum()}")
print(f"  Complete rows : {df[feature_cols].dropna().shape[0]}")

print("\n" + "=" * 70)
print("AUDIT COMPLETE – all files saved to:", OUTPUT_DIR)
print("=" * 70)
