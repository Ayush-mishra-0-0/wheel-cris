I actually think you've just hit what may be the **biggest conceptual shift of the project**.

And I think you're right to question the target itself.

---

## The current target is

> Predict **next diameter degradation**.

But ask yourself:

**Does the railway turn a wheel because of diameter alone?**

No.

A wheel is condemned or reprofiled because it violates **any critical engineering constraint**.

For example:

* Diameter ↓ below limit
* Flange thickness ↓ below limit
* Flange height ↑ beyond limit
* Root wear ↑
* Tread hollow ↑
* QR out of limits
* Flat spots
* Surface defects

The maintenance decision is **multi-dimensional**.

---

## You're currently modeling

```text
Current state
      ↓
Next diameter
```

But the engineer is actually thinking

```text
Current wheel condition
      ↓
Overall wheel health
      ↓
Can this wheel continue safely?
```

Those are different problems.

---

# Think of the wheel as a system

Instead of six independent measurements

```text
Diameter

Flange

Root

Tread

QR

Hollow
```

Think

```text
          Wheel Health
        /     |      \
Diameter Flange Root ...
```

Wheel Health becomes a **latent engineering state**.

---

# Then RUL becomes

Not

> Remaining diameter

Instead

> Remaining **healthy operating life** before any engineering limit is violated.

That's much closer to what maintenance planners actually care about.

---

# I would redefine the prediction hierarchy.

### Level 1

Predict future measurements

```text
Diameter(t+1)

Flange(t+1)

Root(t+1)

Tread(t+1)
```

These are engineering forecasts.

---

### Level 2

Compute Wheel Health

Using engineering rules

Example (illustrative):

```text
Health = f(
remaining diameter,
remaining flange,
remaining QR,
remaining tread,
...)
```

This isn't necessarily learned.

It can be engineered.

---

### Level 3

Predict RUL

Now ask

> When will **Wheel Health** cross the maintenance threshold?

Not

> When will diameter reach X?

---

# This also explains your RMSE plateau.

Right now you're asking the model to predict

```text
Diameter
```

while the maintenance decision depends on

```text
Diameter

+

Flange

+

Root

+

Tread

+

QR
```

You're asking a narrower question than the business actually cares about.

---

# There are two possible directions.

## Option A

### Multi-output regression

Predict

```text
Diameter

Flange

Root

Tread

QR
```

simultaneously.

Advantages

* Shared representation
* Correlated degradation
* Better engineering consistency

---

## Option B (my favorite)

Don't predict measurements.

Predict

```text
Wheel Health Index
```

Then

derive maintenance recommendations.

For example

```text
Health = 84%

↓

Remaining Healthy Distance

↓

Maintenance Priority
```

---

# Even better...

You already built

```text
Exposure

Physics

Maintenance

Geometry
```

Those don't naturally predict

only diameter.

They predict

**overall degradation**.

That's a much better match.

---

# Imagine the dashboard

Instead of

```
Predicted Diameter

1087 mm
```

you show

```
Wheel Health

72%

Main contributors

• Diameter margin 35%

• Flange wear 28%

• Root wear 18%

• Tread hollow 12%

• QR 7%

Expected maintenance

≈18,000 km
```

Now an engineer immediately understands **why**.

---

# I think the research question should evolve.

Instead of

> Can we predict diameter degradation?

I'd ask

> **Can we model the evolution of overall wheel health from operational exposure, maintenance history, and engineering measurements?**

That's a much stronger research question.

---

# My recommendation

I **wouldn't abandon your current diameter model**. It's still valuable as a benchmark and a component of the system.

But I **would make it one part of a larger framework**:

```text
Operational Exposure
        │
        ▼
Future Wheel State
        │
        ▼
Wheel Health Index
        │
        ▼
Remaining Useful Life
        │
        ▼
Maintenance Recommendation
```

I actually think this aligns much better with how railway engineers make decisions. They don't decide based on one measurement in isolation—they assess whether the **wheel, as a whole, remains within safe engineering limits**. If your system can model that evolving health state, the RUL prediction becomes a consequence of the health model rather than the primary objective. That is a stronger engineering formulation and, in my view, a more impactful end goal.
