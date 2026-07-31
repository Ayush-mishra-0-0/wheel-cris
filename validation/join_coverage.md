# Join Coverage

**Status:** In progress.

Track coverage at each stage, with numerator, denominator, exclusions and a
source snapshot ID:

- measurement → equipment master;
- equipment → locomotive assignment;
- measurement → assignment interval (point in time);
- locomotive-time interval → RTIS mileage;
- locomotive-time interval → emergency event;
- measurement/loco time → maintenance and defect events.
