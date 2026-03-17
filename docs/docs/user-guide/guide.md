# User Guide

Automatically generated from downloaded markdown sources.


## 1 Emission Factors Freight Vehicles

# Emission Factors for Freight Vehicles

## Definitions

- **Vehicle Type**  
  Classification of freight vehicles based on their gross vehicle weight (GVW).

- **Gross Weight (GVW)**  
  Gross Vehicle Weight (GVW) is the maximum allowable combined mass of the vehicle chassis, transported material (payload), fuel, accessories, and occupants, expressed in tonnes (t).

- **Vehicle Capacity**  
  Maximum cargo (payload) the vehicle can carry, in tonnes (t).  

- **Empty Vehicle Weight**  
  Calculated as: `Empty Weight = Gross Weight − Capacity`.

- **Emission Factor (kg CO₂/tonne-km)**  
  Average carbon dioxide emissions produced per tonne of freight transported over one kilometre.

- **Total Emissions Formula (Round Trip)**  
  Assuming the vehicle goes fully loaded to the site and returns empty:

```

Total Emissions = Number of Trips × (2 × Empty Vehicle Weight + Cargo Capacity) × Distance × Emission Factor

```

- **Source**  
Reference document from which the emission factors are derived.

---

## Emission Factors by Vehicle Category

| Vehicle Type        | Gross Weight Range (t) | Vehicle Class   | Emission Factor (kg CO₂/tonne-km) | Source |
|-------------------|----------------------|----------------|---------------------------------|--------|
| Light Duty Vehicle | < 4.5                | LDV            | 1.2                             | Transport. In: *Climate Change 2014: Mitigation of Climate Change*, IPCC |
| Heavy Duty Vehicle | 4.5 – 9              | HDV (Small)    | 0.7                             | Transport. In: *Climate Change 2014: Mitigation of Climate Change*, IPCC |
| Heavy Duty Vehicle | 9 – 12               | HDV (Medium)   | 0.55                            | Transport. In: *Climate Change 2014: Mitigation of Climate Change*, IPCC |
| Heavy Duty Vehicle | > 12                 | HDV (Large)    | 0.19                            | Transport. In: *Climate Change 2014: Mitigation of Climate Change*, IPCC |

---

### Notes

1. Choose the **vehicle type and class** based on the Gross Vehicle Weight (GVW).  
2. Use the **emission factor** corresponding to the vehicle type and class for calculating freight emissions.  
3. The formula above assumes a **fully loaded outbound trip** and an **empty return trip**, which is standard in logistics carbon accounting.
