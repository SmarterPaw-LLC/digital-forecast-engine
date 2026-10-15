# Cube math for the Q4 Meowijuana US restock vs AWD decision.
# Dims from the Amazon Break-Even ACOS export (Fee Preview, as-of 2026-09-29).
# All Meowi dims are in INCHES per the Dim Unit column.

HEADROOM = 176.0   # Meowijuana US: 800.05 cu ft at 78% utilized

# sku, label, L, M, S (inches), wt_lb, caitlyn_qty, jason_qty, awd_ok
SKUS = [
    ("CF312",   "Catnip Spray 3 oz",            5.16, 2.01, 1.73, 0.22, 2100, 3500, False),
    ("CF007",   "Meowi-Waui",                   5.87, 2.05, 2.01, 0.18, 2000, 2000, True),
    ("CF102",   "Catnip Buds (jar)",            4.88, 4.17, 3.58, 0.35,  180,  540, True),
    ("CF104",   "Silvervine Sticks",            6.65, 3.23, 0.63, 0.07,   48,  144, True),
    ("MTCM012", "Purrfect Pairings Spray Trio", 6.61, 5.04, 1.73, 0.68,   80,  300, False),
    ("CB2583",  "Purr-Effect Trio Pack",       11.42, 6.73, 2.36, 0.42,  250,  250, True),
    ("CF128",   "Catnip Rollies King Size",     6.54, 3.07, 0.59, 0.04,  168,  168, True),
    ("CB2586",  "Rollies 2-Pack",               8.50, 5.28, 1.22, 0.15,   60,   60, True),
    ("MTCM041", "Crunchie Munchies Trio",      11.30, 9.06, 1.46, 0.77,   50,   50, True),
    ("CF701",   "Whack 'n' Roll",               1.97, 1.57, 1.18, 0.31,   24,   24, True),
    ("CF226",   "Jump 'n' Jamb Deep Sea Squid", 9.21, 6.22, 1.73, 0.15,   60,   60, True),
    ("CF006",   "Feline Frost",                 5.98, 2.01, 1.97, 0.13,   24,   24, True),
    # Caitlyn's AWD proposal adds Pawty Mix, which is NOT on the FBA send list
    ("CF103",   "Catnip Pawty Mix (jar)",       4.76, 3.66, 3.62, 0.53,    0, 1900, True),
]

def cuft(l, m, s):
    return (l * m * s) / 1728.0

print("=" * 108)
print("MEOWIJUANA US SEND LIST  -  CUBE vs 176 cu ft HEADROOM")
print("=" * 108)
print(f"{'SKU':<9}{'Product':<30}{'cuft/u':>9}{'Caitlyn':>9}{'cu ft':>9}{'Jason':>8}{'cu ft':>9}{'lb':>9}  AWD")
print("-" * 108)

tot_c = tot_j = 0.0
tot_c_wt = tot_j_wt = 0.0
for sku, label, l, m, s, wt, qc, qj, awd in SKUS:
    cu = cuft(l, m, s)
    cc, cj = cu * qc, cu * qj
    tot_c += cc; tot_j += cj
    tot_c_wt += wt * qc; tot_j_wt += wt * qj
    print(f"{sku:<9}{label:<30}{cu:>9.5f}{qc:>9,}{cc:>9.1f}{qj:>8,}{cj:>9.1f}{wt*qj:>9,.0f}  {'yes' if awd else 'NO (DG)'}")

print("-" * 108)
print(f"{'':<39}{'TOTAL':>9}{'':>9}{tot_c:>9.1f}{'':>8}{tot_j:>9.1f}{tot_j_wt:>9,.0f}")
print()
print(f"Caitlyn's quantities : {tot_c:7.1f} cu ft  vs {HEADROOM:.0f} free  ->  {'OVER by %.1f' % (tot_c-HEADROOM) if tot_c>HEADROOM else '%.1f cu ft to spare' % (HEADROOM-tot_c)}")
print(f"Jason's quantities   : {tot_j:7.1f} cu ft  vs {HEADROOM:.0f} free  ->  {'OVER by %.1f' % (tot_j-HEADROOM) if tot_j>HEADROOM else '%.1f cu ft to spare' % (HEADROOM-tot_j)}")
print()

# --- Scenario: route Caitlyn's three blends to AWD -------------------------
awd_rec = {"CF103": 1900, "CF007": 3000, "CF102": 900}
print("=" * 108)
print("SCENARIO: Caitlyn's AWD proposal (Pawty Mix 1,900 / Meowi-Waui 3,000 / Buds 900)")
print("=" * 108)
awd_cube = 0.0
for sku, label, l, m, s, wt, qc, qj, awd in SKUS:
    if sku in awd_rec:
        cu = cuft(l, m, s); q = awd_rec[sku]
        awd_cube += cu * q
        print(f"  {sku:<9}{label:<30}{q:>7,} u  x {cu:.5f} = {cu*q:>7.1f} cu ft")
print(f"  {'':<39}{'AWD total':>12} = {awd_cube:>7.1f} cu ft")
print()

# FBA list with the blends pulled out, at Jason's quantities
fba_only = sum(cuft(l,m,s)*qj for sku,_,l,m,s,_,_,qj,_ in SKUS if sku not in awd_rec)
print(f"Remaining FBA send (Jason's qty, blends removed): {fba_only:.1f} cu ft vs {HEADROOM:.0f} free")
print(f"  -> {'OVER by %.1f cu ft' % (fba_only-HEADROOM) if fba_only>HEADROOM else '%.1f cu ft to spare' % (HEADROOM-fba_only)}")
print()

# --- Sprays alone ---------------------------------------------------------
spray = sum(cuft(l,m,s)*qj for sku,_,l,m,s,_,_,qj,awd in SKUS if not awd)
print(f"Sprays alone (CF312 3,500 + MTCM012 300, cannot go AWD): {spray:.1f} cu ft")
print(f"  -> {spray/HEADROOM*100:.0f}% of the 176 cu ft headroom")
