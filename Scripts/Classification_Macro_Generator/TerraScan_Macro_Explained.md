# Understanding the TerraScan Classification Macro

A complete guide to how LiDAR point cloud classification works and what every step of the BC LiDAR production macro does.

---

## LiDAR Fundamentals — The 60-Second Version

A LiDAR sensor on an aircraft fires laser pulses at the ground. Each pulse travels down, hits something (ground, a tree, a building roof), and bounces back. The sensor records:

- **XYZ coordinates** — where the reflection happened in 3D space
- **Return number** — a single pulse can hit a tree canopy (1st return), a branch (2nd return), and then the ground (3rd return). These are called "multiple returns."
- **Scan angle** — the angle of the laser beam relative to straight down (nadir). Beams fired at steep angles to the side are less accurate.
- **Point Source ID** — which flight line captured this point. The aircraft flies back and forth in strips, and strips overlap. Each strip gets a unique ID.
- **Intensity** — how strong the reflection was

The raw data is just a massive cloud of XYZ points — millions per tile. **Classification** is the process of labeling each point: "this is ground," "this is a tree," "this is noise." The ASPRS standard defines class codes:

| Class | Meaning |
|-------|---------|
| 0 | Never Classified |
| 1 | Unclassified (processed but not assigned) |
| 2 | Ground |
| 3 | Low Vegetation (0-10 cm above ground) |
| 4 | Medium Vegetation (10 cm-1 m) |
| 5 | High Vegetation (above 1 m) |
| 6 | Building |
| 7 | Low Point (noise) |
| 12 | Overlap |

---

## The Macro — Step by Step

### Header Block

```
[TerraScan macro]
Version=020.001
Author=Spencer Floyd
ByLine=0 / ByScanner=0 / SlaveCanRun=0 / etc.
```

This is just metadata. It tells TerraScan this is a macro file, who wrote it, and that it should process all points together (not separated by flight line or scanner). Not classification-related.

---

### Phase 1: Reset Everything

```
FnScanClassifyClass("Any",0,0)
```

**What it does:** Takes every single point regardless of current class ("Any") and sets it to Class 0 (Never Classified).

**Why:** This is a clean slate. If the data was previously classified (by the vendor, or a previous macro run), this wipes all labels so you start fresh. Without this, old labels would contaminate your results.

---

### Phase 2: Thin Duplicate Points

```
FnScanThinPoints("Any",9997,2,0,0.001,0.001,0)
```

**What it does:** Finds points that are virtually on top of each other (within 0.001m = 1mm horizontally and vertically) and moves the extras to Class 9997 (a custom "parking" class, out of the way).

**Why:** Sometimes the sensor records duplicate points at the exact same location. These duplicates add no information and can confuse ground-finding algorithms. This removes them from consideration without deleting them.

**Parameters broken down:**

- `"Any"` — check all classes
- `9997` — move duplicates to this class
- `2` — thinning mode (2D grid-based)
- `0.001, 0.001` — the XY and Z tolerance (1mm)

---

### Phase 3: Initial Noise Removal

```
FnScanClassifyIsolated("0",7,5,"0",3.00,0)
```

**What it does:** Looks at every Class 0 point. For each one, it counts how many other Class 0 points exist within a 3-meter 3D sphere. If fewer than 5 neighbors are found, the point is classified as Class 7 (Low Point / Noise).

**Why:** Real objects (ground, trees, buildings) produce clusters of points. A point floating alone in space — far from any other points — is almost certainly sensor noise or a bird or a reflection off dust. This catches the obvious junk early.

**Think of it as:** "If you're alone in a 3m bubble, you're probably noise."

---

### Phase 4: Per-Flight-Line Overlap Detection

This is the most complex section. It loops over every unique Point Source ID (flight line):

```
for each point_id:
    Keyin: scan display view=1/lineoff=all        # Turn OFF all flight lines
    Keyin: scan display view=1/lineon={point_id}   # Turn ON only this one line

    FnScanClassifyClass("0",6,1)
    FnScanClassifyCloseby("6","0-65535","0-255",0,3,1.500,0,0,1,"0",0,"0-65535",0,"0-255",0)
    FnScanClassifyClass("6",7,0)
```

Here's what happens for each flight line:

**Step A — Isolate one line:**
The `Keyin` commands are MicroStation commands that control which flight lines are visible/active. "Turn off all lines, then turn on only line #X." This means the next commands only operate on points from that single flight strip.

**Step B — `FnScanClassifyClass("0",6,1)`:**
Temporarily move all Class 0 points (on this line only) to Class 6. The `1` at the end means "only displayed points" — so only points from this flight line.

**Step C — `FnScanClassifyCloseby`:**
This is the core overlap detection. For each Class 6 point, it looks for nearby Class 0 points (from OTHER flight lines, which are still Class 0 because they weren't displayed). The 1.5m radius means: "If a Class 6 point has a Class 0 neighbor within 1.5 meters, it's NOT an overlap point — it has corroboration from another flight line, so move it back to Class 0."

Points that remain Class 6 after this step are points that exist ONLY on this flight line with no nearby match from other lines — meaning they're in an overlap zone and are the "worse" duplicate.

**Step D — `FnScanClassifyClass("6",7,0)`:**
Any points still in Class 6 (the overlap rejects) get sent to Class 7 (Noise).

**The overall logic:** For each flight strip, check if its points are corroborated by another overlapping strip. Points that only appear in one strip's overlap zone (no matching point from the other strip nearby) are considered redundant/noisy and get removed. This is critical because where flight strips overlap, you get double-coverage, and the points at the edges of each strip (high scan angle, less accurate) should be removed in favor of the other strip's better-angle points.

---

### Phase 5: Scan Angle Filtering

```
FnScanClassifyAngle("Any",12,0,-29.00,-99.99,0)
FnScanClassifyAngle("Any",12,0,29.00,99.99,0)
```

**What it does:** Any point collected at a scan angle beyond +/-29 degrees from nadir (straight down) gets classified as Class 12 (Overlap).

**Why:** Picture the laser beam. When pointed straight down, it hits the ground at a right angle — maximum accuracy. As the scanner sweeps to the sides, the angle increases. At extreme angles (near the edge of the swath), the laser beam hits the ground at a shallow angle, the footprint elongates, positional accuracy drops, and there's more chance of hitting the side of objects rather than the top. The +/-29 degree cutoff removes these low-quality edge-of-swath points.

**Visual:**

```
        Aircraft
          |
    ______|______
   /   29 |29    \    <-- Good zone (kept)
  / Beyond| Beyond\   <-- Bad zone (removed)
 /________|________\
     Ground
```

---

### Phase 6: Low Point Removal (3 Passes)

```
FnScanClassifyLow("0",7,6,0.30,5.00,0)
FnScanClassifyLow("0",7,6,0.30,5.00,0)
FnScanClassifyLow("0",7,6,0.30,5.00,0)
```

**What it does:** For each Class 0 point, the algorithm looks at neighboring points within a 5-meter radius. If a point is more than 0.30 meters BELOW its neighbors, and the group of low points is 6 or fewer, it's classified as Class 7 (Noise).

**Why:** Some laser pulses bounce off things they shouldn't — multi-path reflections (the beam bounces off a surface, then off another surface, then back to the sensor, making the point appear deeper than it really is), water surfaces, or sensor glitches. These create points that sit anomalously below the real ground surface. They'd wreck your ground model if left in.

**Why 3 times?** Each pass can only catch points that are low relative to their current neighbors. Once you remove one layer of low points, previously-hidden low points may now stand out as anomalous relative to the updated neighborhood. Running it 3 times catches progressively deeper noise. Think of peeling layers.

**Parameters:**

- `"0"` — only check unclassified points
- `7` — send noise to Class 7
- `6` — max group size. If MORE than 6 points are all low together, they might be a real feature (a ditch, a creek bed) rather than noise, so they're left alone
- `0.30` — must be at least 30cm below neighbors
- `5.00` — search radius of 5 meters

---

### Phase 7: Secondary Isolated Point Removal

```
FnScanClassifyIsolated("0",7,30,"0",15.00,0)
FnScanClassifyIsolated("0",7,15,"0",5.00,0)
```

**What it does:** Two more passes of isolation filtering, now with different thresholds:

1. **First:** within a 15m sphere, if fewer than 30 neighbors -> noise
2. **Second:** within a 5m sphere, if fewer than 15 neighbors -> noise

**Why:** The initial isolated-point pass (Phase 3) used tight parameters (5 neighbors, 3m). Now that overlap and low-point noise have been removed, these broader passes can catch larger clusters of noise that weren't isolated enough before. The first pass catches sparse areas at a large scale; the second catches smaller sparse clusters.

---

### Phase 8: Ground Classification

```
FnScanClassifyGround("0",2,"2",1,40.0,89.00,10.00,1.50,1,5.0,0,2.0,0,0,0)
```

**This is the most important step in the entire macro.** It identifies which points are bare earth (ground).

#### How TerraScan's ground algorithm works (TIN-based progressive densification):

**1. Initial surface:** The algorithm divides the area into a grid of cells (40m x 40m, controlled by the building size parameter). In each cell, it picks the **lowest point** as a "seed" ground point. These seeds form an initial very rough triangulated surface (TIN — Triangulated Irregular Network, a mesh of triangles connecting points).

**2. Iterative densification:** The algorithm then looks at every remaining unclassified point and asks: "Could this point be ground?" It checks two things:

- **Iteration angle (10.00 degrees):** The angle between the point and the nearest triangle surface. If the point sits on a slope steeper than 10 degrees relative to the existing ground surface, it's rejected. This prevents buildings and vegetation from being called ground.
- **Iteration distance (1.50m):** The vertical distance from the point to the triangle surface. If the point is more than 1.5m above the surface, it's rejected.

**3. Points that pass both tests** get added to the ground class, the TIN is rebuilt with the new points, and the process repeats until no more points qualify.

#### Parameter breakdown for the Regular macro:

| Parameter | Value | Meaning |
|-----------|-------|---------|
| FromClass | "0" | Only consider unclassified points |
| ToClass | 2 | Classify as Ground |
| InitLow | "2" | Initial seed selection method |
| BldSz | 40.0m | Grid cell size for finding lowest seeds |
| MaxAng | 89.00 degrees | Max terrain angle allowed (nearly vertical — very permissive) |
| IterAng | 10.00 degrees | Max angle a new point can make with existing surface |
| IterDst | 1.50m | Max distance above existing surface |
| Reduce | 1 | Enable surface reduction |
| RedLen | 5.0 | Reduction distance |
| Stop | 0 | Stop condition |
| StopLen | 2.0 | Stop distance |

#### Urban macro difference:

The Urban macro uses `BldSz=200m, IterAng=7 degrees`. The 200m building size means the algorithm looks for seed ground points in a 200m grid instead of 40m. This is because urban areas can have large buildings — if your grid cell is only 40m and a building fills it entirely, the lowest point in that cell is on the building roof, and the algorithm would incorrectly use the roof as ground. 200m ensures at least some actual ground is found in each cell. The lower iteration angle (7 degrees vs 10 degrees) makes the algorithm more conservative — it won't follow steep surfaces as aggressively, which prevents it from "climbing up" building walls and calling them ground.

---

### Phase 9: High Outlier Detection and Cleanup

```
FnScanClassifyHgtGrd(2,100.0,0,13,15.000,100000.000,0)
FnScanClassifyIsolated("13",7,15,"0,13",5.00,0)
FnScanClassifyClass("13",0,0)
```

**Step 1:** Find all unclassified points that are between 15m and 100,000m above the ground surface (using ground TIN with max edge length 100m). Temporarily put them in Class 13.

**Why:** Points floating extremely high above ground (>15m) are suspicious. They could be aircraft, birds, atmospheric returns, or sensor errors. By parking them in a temporary class, you can examine them separately.

**Step 2:** Of those Class 13 points, check if they're isolated (fewer than 15 neighbors within 5m among Class 0+13 points). If isolated -> Class 7 (Noise). These are truly junk — high AND alone.

**Step 3:** Everything remaining in Class 13 (high but NOT isolated — probably legitimate tall objects like communication towers, tall buildings, power lines) gets moved back to Class 0 for normal vegetation classification in the next phase.

**Think of it as:** "Flag everything super high, remove the obvious junk, then give the rest benefit of the doubt."

---

### Phase 10: Height-Based Vegetation Classification

```
FnScanClassifyHgtGrd(2,15.0,0,3,0.000,0.100,0)
FnScanClassifyHgtGrd(2,15.0,0,4,0.100,1.000,0)
FnScanClassifyHgtGrd(2,15.0,0,5,1.000,1000000.000,0)
```

**What it does:** Measures each remaining unclassified point's height above the ground surface (the TIN from Phase 8), using a max TIN edge of 15m, and assigns classes based on height:

| Height Above Ground | Class | Label |
|---------------------|-------|-------|
| 0.0 - 0.1 m | 3 | Low Vegetation (grass, moss) |
| 0.1 - 1.0 m | 4 | Medium Vegetation (shrubs) |
| 1.0 m+ | 5 | High Vegetation (trees) |

**Why these thresholds?** They're the ASPRS standard. 10cm is roughly the height of grass/ground cover. 1m is roughly the boundary between shrubs and trees.

**The 15m max TIN edge:** When computing height above ground, the algorithm builds a TIN from ground points. If a triangle edge is longer than 15m (meaning ground points are sparse in that area), the algorithm won't interpolate the ground surface there — it's too uncertain. This prevents nonsensical height calculations in areas with poor ground coverage (dense forest canopy, water bodies).

---

### Phase 11: Extreme High Point Removal

```
FnScanClassifyHgtGrd(2,500.0,9999,7,400.000,1000000.000,0)
```

**What it does:** Any point more than 400m above ground gets classified as Noise (Class 7). Uses a very large TIN edge (500m) and processes from any class (9999 = all).

**Why:** Nothing legitimate in BC LiDAR is 400m above ground level. This catches any remaining atmospheric returns or extreme sensor errors that survived all previous filters.

---

### Phase 12: Finalize Unclassified

```
FnScanClassifyClass("0",1,0)
```

**What it does:** Any points still sitting in Class 0 (Never Classified) get moved to Class 1 (Unclassified — meaning "processed but not assigned a category").

**Why:** This is housekeeping. Class 0 means "never touched." Class 1 means "we looked at it but it doesn't fit ground/vegetation/noise." This distinction matters for quality control — after the macro runs, there should be zero Class 0 points. If there are, something went wrong.

---

## The PRJ File

The `.prj` file is a TerraScan project configuration, not classification logic:

```
Scanner=AirborneLidar        -> Data type
Storage=LAS1.4               -> File format (ASPRS standard)
StoreTime=2                  -> Store GPS timestamps
BlockSize=1000               -> Tile size in meters (1km x 1km)
BlockRounded=1               -> Tile boundaries snap to round numbers
```

This tells TerraScan how to interpret and organize the data files. It doesn't affect classification.

---

## The Complete Pipeline Visually

```
Raw Points (all Class 0)
    |
    +-- Phase 1:  Reset all -> Class 0
    +-- Phase 2:  Remove exact duplicates -> Class 9997
    +-- Phase 3:  Remove lonely points (5 neighbors, 3m) -> Class 7
    +-- Phase 4:  Per-line overlap detection -> Class 7
    +-- Phase 5:  Remove steep-angle points (>29 deg) -> Class 12
    +-- Phase 6:  Remove below-surface noise (x3) -> Class 7
    +-- Phase 7:  Remove sparse clusters (2 passes) -> Class 7
    +-- Phase 8:  GROUND CLASSIFICATION -> Class 2
    +-- Phase 9:  Flag/clean extreme heights (temp Class 13) -> Class 7 or back to 0
    +-- Phase 10: Vegetation by height -> Classes 3, 4, 5
    +-- Phase 11: Remove 400m+ outliers -> Class 7
    +-- Phase 12: Remaining -> Class 1

Final result: Every point has a class label.
```

The key insight is that the macro works like a funnel — it removes noise and bad data in layers (Phases 2-7), THEN classifies the clean points (Phases 8-12). The order matters: if you tried to classify ground before removing noise, the noise points would corrupt your ground surface.
