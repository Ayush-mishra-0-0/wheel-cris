These plots are actually **more revealing than the RMSE**. They tell us *why* you're at 22.9 instead of just telling us the number.

I'll go through them one by one.

---

# 1. Prediction vs Actual Scatter

This is the one that immediately caught my eye.

The cloud is concentrated around

```
Predicted ≈ 1000–1100
Actual    ≈ 1020–1085
```

That is expected because **most wheels are healthy most of the time**.

However, one thing worries me.

### There are extreme predicted values

You have points like

```
Prediction = 1600 mm

Actual = 1078 mm
```

and

```
Prediction = 120 mm

Actual = 1050 mm
```

A railway wheel **cannot** suddenly become

* 1600 mm
* 120 mm

Those are physically impossible.

---

## This suggests something important.

I don't think the model is broken.

I think **those are outliers**.

I would immediately inspect those records.

Questions:

* Was the feature vector corrupted?
* Missing values?
* Encoding bug?
* Extrapolation outside training distribution?
* Wheel schedule one-hot issue?

These points alone can increase RMSE.

---

# 2. Residual Plot

This one is extremely informative.

A good residual plot should look like

```
      •
 •   •   •
----------------
 • •   •
```

Random.

Yours looks like

```
\
 \
  \
   \
    \
```

Almost a straight diagonal.

That means

> **Residual depends on prediction.**

This is called **systematic bias**.

The model

* over-predicts large values
* under-predicts small values

This usually means one of these:

### A)

Target distribution is skewed.

### B)

Important variables are missing.

### C)

Linear model cannot explain the variance.

Given your project,

I strongly believe it's **B**.

---

# 3. RMSE by interval

This surprised me.

I expected

```
0-30

↓

30-60

↓

60-90

↓

180+
```

to steadily increase.

Instead

```
23

25

22

21

25

23
```

Almost flat.

That's actually **good news**.

It means

> Long inspection intervals are **not** your main problem.

Earlier we suspected they might be.

The data says otherwise.

---

# The biggest conclusion

Look at all three plots together.

They tell a very consistent story.

## The model has learned

✔ fleet trend

✔ average behaviour

✔ interval effects

---

It has **not** learned

✔ sudden degradation

✔ extreme wear

✔ maintenance-driven jumps

---

Those require

* distance
* braking
* curvature
* load
* operational exposure

Exactly what you're planning for Phase 2.

---

# One thing I would investigate tomorrow

Those impossible predictions.

Seriously.

Run

```python
predictions.sort_values("prediction").head(20)

predictions.sort_values("prediction").tail(20)
```

Inspect

* wheel ID
* home shed
* interval
* features
* actual

I suspect you'll find

either

* corrupted rows

or

* unseen feature combinations.

---

# Another thing

Compute

```
R²
```

I'm very curious.

Because

RMSE alone

doesn't tell us

how much signal exists.

---

# What I think is happening

I think your current model is solving roughly

```
Diameter Loss

=

f(

time,

maintenance,

wheel age,

inspection history

)
```

But the real equation is probably closer to

```
Diameter Loss

=

f(

time,

distance,

curvature,

gradient,

load,

braking,

wheel profile,

maintenance,

weather,

track quality,

inspection history

)
```

You're asking the model to solve a much harder problem with only about **30–40% of the explanatory variables**.

---

# The most exciting part

This is where I became optimistic.

**Linear Regression is the best model.**

Most people would think

> "That's bad."

I think

> "That's fantastic."

Because it means

**you haven't reached the algorithm ceiling.**

If XGBoost, CatBoost, Random Forest, and Linear all gave almost identical results *after* you had 80 engineered features, then I'd worry.

Instead, you're at:

```
15 features
↓

Linear wins
```

That's exactly what I expect from an information-limited problem.

---

# If this were my project

I would **freeze V1 today**.

No more tuning.

No more trying different regressors.

No more hyperparameter search.

Instead I'd spend the next month collecting

* interval distance
* cumulative distance
* route geometry
* axle load
* speed
* braking
* weather

Then I'd rebuild the feature store as **V2**.

---

# One final recommendation

I actually think your next milestone should **not** be "Improve RMSE."

It should be:

> **Explain 80% of the largest prediction errors.**

For each of the worst 100 regression errors, classify the root cause:

* Data quality issue
* Missing operational exposure (distance, route, load, etc.)
* Maintenance event not represented in features
* Model limitation
* Unknown

If, for example, you find:

| Cause                        | Percentage |
| ---------------------------- | ---------: |
| Missing distance information |        42% |
| Missing route information    |        21% |
| Data quality problems        |        18% |
| Maintenance semantics        |        11% |
| Unknown                      |         8% |

then you've created a **roadmap for improving the model that's based on evidence**, not guesswork.

That's much more valuable than reducing RMSE from **22.9 to 22.5** by tweaking hyperparameters. It tells you exactly **which missing information is preventing the model from making better engineering decisions**, and that aligns perfectly with your Phase 2 plan.
