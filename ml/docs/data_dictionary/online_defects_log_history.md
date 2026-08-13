# Data Dictionary: online_defects_log_history

| Column | Type | Null count | Null % | Distinct | Candidate key | Sample values | Min | Max | Mean | Comments |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |
| HistoryOldId | int64 | 0 | 0.0000 | 376,660 | True | ["1", "2", "3", "4", "5"] | 1 | 401946 | 192699.776339 |  |
| OldId | int64 | 0 | 0.0000 | 138,710 | False | ["480486", "466632", "463930", "461207", "455449"] | 18074 | 562421 | 470900.972176 |  |
| OldType | float64 | 37,892 | 10.0600 | 25 | False | ["17.0", "29.0", "24.0", "21.0", "27.0"] | 1.0 | 35.0 | 20.579305 |  |
| OldLocoId | float64 | 9,629 | 2.5564 | 14,846 | False | ["9631.0", "9816.0", "9283.0", "1648.0", "3259.0"] | 8.0 | 24513.0 | 9302.654539 |  |
| OldDateOccurance | datetime64[us] | 7 | 0.0019 | 113,752 | False | ["2025-11-06T00:52:00", "2025-09-29T01:51:00", "2025-09-22T13:35:00", "2025-09-13T00:14:00", "2025-08-25T05:02:00"] | 1900-01-01T00:00:00 | 2026-07-24T14:55:00 |  |  |
| OldInspector | str | 56,556 | 15.0151 | 1,344 | False | ["RTIS", "SAN297", "KURTLC", "ASNCHG", "ACHLES"] |  |  |  |  |
| OldSectionPresent | str | 7,791 | 2.0684 | 18,351 | False | ["", "HIJ-HIJ", "UDN-UDN", "BBS-BBS", "RMZ-PDSN"] |  |  |  |  |
| OldZone | float64 | 1,302 | 0.3457 | 20 | False | ["3.0", "12.0", "16.0", "15.0", "9.0"] | -1.0 | 20.0 | 9.394783 |  |
| OldDivision | float64 | 175 | 0.0465 | 76 | False | ["11.0", "49.0", "63.0", "13.0", "60.0"] | -1.0 | 82.0 | 37.71916 |  |
| OldRepercussion | float64 | 188,476 | 50.0388 | 3 | False | ["-1.0", "0.0", "1.0"] | -1.0 | 1.0 | -0.924271 |  |
| OldDetention | float64 | 316 | 0.0839 | 1,344 | False | ["0.0", "111.0", "47.0", "92.0", "5.0"] | -28635.0 | 63072.0 | 55.175018 |  |
| OldOccrance | str | 1 | 0.0003 | 155,912 | False | ["ECRW", "111\" HIJ DUE TO LP REPORTED AT 20:17 LEADING CAB HORN  NOT WORKING AND \r\n AS PER MEMO FROM TLC/ KGP AT 20:40 HRS RELIEF LOCO  FOR 15640 DEMANDED,  LOCO NO-37241/BNDM/WAP-7, POWER OF N/DPCB WILL BE PROVIDED.N/DPCB HIJ ARRIVED AT 21.15 HRS, LOCO DETACHED AT 21.25, EOT AND READY AT 22.00 HRS, DEP-22.06 HRS", " #  GPS Last updated at UDN on 22-Sep-2025 09:16:38", "SWITCHED_OFF", " #  GPS Last updated at BBS on 25-Aug-2025 02:39:08"] |  |  |  |  |
| OldActionTaken | str | 131,362 | 34.8755 | 42,522 | False | ["MCB down, As per next loco working link, At mean time case is lodged wrongly on loco/crew account", "System: Analysis Not Required", "No loco trouble", "", "Compressor-1 MCB 47.1/1 tripped frequently. Due to unbalanced output voltage of BUR-3 this incident occurred. Engine crew isolated BUR-3 by tripping MCB 127.22/3 and in load sharing compressors transferred from BUR-3 to BUR-2 and problem got rectified.\nTo generate unbalanced output voltage  by BUR-3"] |  |  |  |  |
| OldDateReady | datetime64[us] | 318,403 | 84.5333 | 41,724 | False | ["2025-11-03T15:50:44.330000", "2025-06-17T17:31:09.967000", "2023-08-31T19:25:00", "2025-10-27T06:45:00", "2025-09-19T16:24:12.337000"] | 2008-09-14T12:00:00 | 2026-07-24T11:56:30.760000 |  |  |
| OldService | float64 | 188,683 | 50.0937 | 10 | False | ["-1.0", "4.0", "2.0", "1.0", "3.0"] | -1.0 | 9.0 | -0.311836 |  |
| OldDeadMove | float64 | 357,796 | 94.9918 | 3 | False | ["1.0", "0.0", "2.0"] | 0.0 | 2.0 | 0.457273 |  |
| OldSectionOccurence | str | 376,533 | 99.9663 | 95 | False | ["MGS yd", "", "TATA yd", "SC yd", "TATA"] |  |  |  |  |
| OldArrShed | float64 | 325,282 | 86.3596 | 4 | False | ["0.0", "1.0", "2.0", "-1.0"] | -1.0 | 2.0 | 0.100471 |  |
| OldCreatedBy | float64 | 358,526 | 95.1856 | 173 | False | ["2686.0", "5288.0", "3046.0", "6403.0", "3341.0"] | 1.0 | 11026.0 | 4309.381493 |  |
| OldLastModifiedBy | float64 | 197,325 | 52.3881 | 687 | False | ["3135.0", "3711.0", "10116.0", "3.0", "5288.0"] | 1.0 | 11090.0 | 4673.663317 |  |
| OldLastModifiedOn | datetime64[us] | 113,040 | 30.0112 | 146,336 | False | ["2025-11-10T00:00:00.183000", "2025-10-04T18:20:53.650000", "2025-09-17T00:00:00.707000", "2025-08-10T10:21:36.760000", "2025-08-14T18:20:43.293000"] | 2016-08-13T09:21:07.073000 | 2026-07-24T17:08:35.593000 |  |  |
| OldCreatedOn | datetime64[us] | 98 | 0.0260 | 122,458 | False | ["2025-11-06T05:00:00.453000", "2025-09-30T02:21:44.507000", "2025-09-22T13:40:00.833000", "2025-09-13T23:20:00.700000", "2025-08-25T05:10:00.467000"] | 2016-08-13T09:18:17.967000 | 2026-07-24T15:50:00.370000 |  |  |
| OldFuncLocation | float64 | 43,008 | 11.4183 | 193 | False | ["22.0", "20.0", "23.0", "10.0", "190.0"] | 1.0 | 403.0 | 106.826337 |  |
| OldCrewBeatSection | float64 | 200,905 | 53.3386 | 54 | False | ["-1.0", "1188.0", "1597.0", "1669.0", "725.0"] | -1.0 | 1945.0 | 0.086934 |  |
| OldDirction | float64 | 188,664 | 50.0887 | 4 | False | ["-1.0", "0.0", "1.0", "2.0"] | -1.0 | 2.0 | -0.922046 |  |
| OldGrediant | float64 | 188,668 | 50.0897 | 4 | False | ["-1.0", "3.0", "1.0", "2.0"] | -1.0 | 3.0 | -0.923587 |  |
| OldPunctloss | float64 | 188,549 | 50.0581 | 3 | False | ["0.0", "-1.0", "1.0"] | -1.0 | 1.0 | 0.047988 |  |
| OldFailuerCause | float64 | 188,654 | 50.0860 | 44 | False | ["-1.0", "45.0", "44.0", "20.0", "43.0"] | -1.0 | 48.0 | -0.189552 |  |
| OldFailedBeforeStation | str | 188,679 | 50.0927 | 1,555 | False | ["-1", "8528", "7124", "3988", "7561"] |  |  |  |  |
| OldFailedAfterStation | str | 188,681 | 50.0932 | 1,435 | False | ["-1", "8528", "7124", "3988", "6808"] |  |  |  |  |
| OldWagaonNo1 | str | 200,906 | 53.3388 | 3 | False | ["", "31100753367/ER", "30099363328/SCR"] |  |  |  |  |
| OldWagaonNo2 | str | 200,906 | 53.3388 | 3 | False | ["", "30028398669/ER)", "30079414682/SER"] |  |  |  |  |
| OldWagonLastMajorSch | str | 200,906 | 53.3388 | 1 | False | [""] |  |  |  |  |
| OldWagonLastMajorSchDate | datetime64[us] | 200,906 | 53.3388 | 1 | False | ["1900-01-01T00:00:00"] | 1900-01-01T00:00:00 | 1900-01-01T00:00:00 |  |  |
| OldWagonLastMajorRoH | str | 200,906 | 53.3388 | 1 | False | [""] |  |  |  |  |
| OldWagonLastMajorRoHDate | datetime64[us] | 200,906 | 53.3388 | 1 | False | ["1900-01-01T00:00:00"] | 1900-01-01T00:00:00 | 1900-01-01T00:00:00 |  |  |
| OldFailureAccount | float64 | 200,800 | 53.3107 | 6 | False | ["3.0", "-1.0", "4.0", "5.0", "2.0"] | -1.0 | 5.0 | 2.711128 |  |
| OldBPCIssuedStation | str | 200,906 | 53.3388 | 9 | False | ["", "TKD", "RNY/NFR", "TPGY", "HPT YARD /SWR"] |  |  |  |  |
| OldBPCNo | str | 200,906 | 53.3388 | 5 | False | ["", "50000588661", "50000573596", "50000576710", "1321959"] |  |  |  |  |
| OldBPCDate | datetime64[us] | 200,906 | 53.3388 | 2 | False | ["1900-01-01T00:00:00", "2023-12-05T00:00:00"] | 1900-01-01T00:00:00 | 2023-12-05T00:00:00 |  |  |
| OldMainEqFailed | float64 | 217,284 | 57.6870 | 458 | False | ["0.0", "299.0", "-1.0", "47.0", "547.0"] | -1.0 | 10042.0 | 110.066346 |  |
| OldSubEqFailed | float64 | 217,334 | 57.7003 | 274 | False | ["-1.0", "505.0", "511.0", "524.0", "304.0"] | -1.0 | 837.0 | 10.877622 |  |
| OldShedReport | str | 143,541 | 38.1089 | 25,025 | False | ["", "System: Analysis Not Required", "In Cab?1, the ALP side sander was found not functioning and the LP side sandbox pipe was disconnected. TXR staff attended the issue, reconnected the LP side sandbox pipe, and upon inspection discovered a nozzle jam on the ALP side. The nozzle was cleaned, after which the sander was tested and found to be working.", "BUR3 R phase WRE defective. Same was replaced.\r\nDetails of WRE rake:-\r\nSr. Number:-", "Traffic/wrongly logged"] |  |  |  |  |
| OldCTAReport | str | 200,906 | 53.3388 | 201 | False | ["", "JE Dhiraj Kumar arrived UNDN at 13.00. Loco checked and found, when MP put on 'N', 5/6 notch comes itself in both loco. So jumper disconnected and loco separately one by one tested, found both loco normal. Ready given at 14.50.", "This loco nor in Failure Sheet neither ICMS, e-LOCOS Assets failure, e-LOCOS Punctuality.", "Loco failed on 11.03.25 while working on train no. 54308 at Mehrauli due to Auto regression at 7th and 8th notch. After departure ex-DLI, train stopped at DSA for schedule stoppage. Further LP informed TLC/NDLS that after 7th and 8th notch, auto regression was occurring. LP put HBA on '0' and operated HVCD and then put it in normal position. Loco became normal and train worked further. After some time ex-SBB same problem occurred. LP then cleared block section using mnaual operation of GR and train arrived at GZB. Further same problem continued to come again and again after which loco was declared failed. There was a detention of 67\".\r\n\r\nLoco arrived in shed as dead on 15.03.25. In shed, during LT+HT testing, no any notch stucking or notch regression was observed. However, as per data fault, fault of DJ trip via GR stuck between notches was found logged at the time of failure. Notch related circuit was checked, correspondingly +ve supply input wire no. 082 related to 'ON' notches and +ve supply input wire no. 072 related to 'between' notches. Also, its SMGR was checked and parameters were taken as under -\r\nAuxiliary switches continuity checked and found Ok, regression time - 10 sec (9-13 sec), PRV pressure - 3.4kg/cm2 (2.5-3.5kg/cm2), pressure drop at every notch - 0.4kg/cm2 (maxm 0.5kg/cm2), no any air leakages were noticed over SMGR pipe connections/valves.\r\n\r\nAs several faults such as \"wire no. 259 short circuit\", \"EVPHGH output wire or coil shorted with B\", \"Battery voltage low\", LSGR output  wire or coil shorted with B\", etc. Hence, on a precautionary basis, M657V3DOP#2 (digital output card which supplies 110V +ve supply to coils of various contactors, relays and magnet valves. was interchanged with Spare card no.5 by Medha staff and further escorting will be done by staff. Hence, no any specific faults were noticed over SMGR.\r\nResponsibility - Miscellaneous", "Loco failed on 20.11.24 while working on train no. 04255 in between PRG-PFM due to DJ internal fault and DC link current too high message on display. At 19.35hrs., LP informed that after passing PRG starter signal, train stopped at KM no. 149/38 due to internal fault and DC link current too high coming on display. LP checked SIV unit and found internal fault message flashing, he then put HBA OFF/ON for 05 min after which loco got normal however after sometime again DJ tripped via QSIT, internal fault DC Link current too high. Again, LP put HBA OFF/ON for 05 min but this time fault not rectified. Hence, loco was declared failed and relief power was demanded. There was a detention of 170\".\r\n\r\nAs per fault data of SIV, many times P15 LV fault was recorded dt. 20.11.24 and QSIT had dropped, loco was checked at LKO station on 21.11.24 and found problem in its battery charger GDU Card as it was found flashed, so GDU card was changed along with the Battery charger IGBT (as defective GDU card had overloaded its BCH IGBT). Loco was then checked on full load for approx. 02 hrs. and loco was given fit at 18.00hrs. Details of defective BCH GDU Card -\r\nMake - AAL, S.No. - 23040030, it is covered under AAL AMC.\r\nThus, failure attributed to material failure of Firm AAL failed under AMC.\r\nResponsibility - Material/AAL"] |  |  |  |  |
| OldHQReport | str | 200,903 | 53.3380 | 29 | False | ["", "As per ALP reported, Main power off F0110P1 with BUR2 & BUR3 inverter fault. As per BUR2 inverter fault troubleshooting started with TMB1 & 2 MCB tripping, then Pump converter 1-2 & then Pump transformer 1-2 MCB tripping. But BUR3 isolated 1st & then BUR-2 isolated. After CP1 MCB tripped, at that time VCB hold , MR,BP FP charged. Loco further worked normal up to CSMT without any trouble. \r\n       On arrival at CSMT, DDS downloaded, checked & found 1st BUR3 isolated with inverter fault after that BUR2 isolated with inverter fault resulting in Main power off. Loco checked found CP1 contactor 47.1.2/1 one ph contact tip got melted, due to this single phasing in contactor causing inverter fault in BUR3, BUR 2, subsequently Main power off. 47.2/1 contactor changed & found loco working normal. Same contactor changed & found loco working normal. \r\nDue to improper bedding, contactor tips melted & gap created between fix & moving contact resulting single phase supply. Firm representative called for an investigation.\r\nTroubleshooting for BUR2 inverter fault  & BUR3 inverter fault is different. \r\nIf the crew had described failure in proper manner, takes less time for troubleshooting & above said detention could have been minimised.", "While starting from CHI station, DJ trip with fault message 'Disturbance in processor RBU 4 . MR and BP dropped with Emergency Brake vigilance and MR unable to increased. After CE OFF/ ON, loco become normal but MR unable to increased. Further LP isolated BUR3 and after CE OFF/ ON, further worked normal without any trouble. \r\nLoco checked at VVH trip shed for RBU4 lifesign missing but found normal. BUR3 kept in service and found no abnormalities. \r\nDDS downloaded, checked and found 1st RBU4 lifesign missing fault message logged, afterwards emergency brake vigilance message came and BP MR dropped,  As both CP not worked causing MR unable to increased. So LP performed CE off on again RBU4 isolated and VCD acted. But again due to both CP not working in auto mode, MR not increased. \r\nLP again performed, 2nd CE off on, coincidently RBU4 lifesign was not coming and LP isolated BUR-3, both CP worked, MR increased & further worked normal. \r\nRBU4 card defective, same card changed & found loco working normal. \r\nFollowing things to perform LP while RBU4 lifesign missing, \r\n1. Since both CP not working in auto mode, ECPSW switch(SB1) to operate. Both CP will work in auto mode OR CP can run in manual mode by pressing BLCP switch direct. \r\n2. Vcd to be isolated. \r\nIf LP perform above thing timely/ troubleshoot timely detention could have been avoided.", "ATS KTCE M/L-23.56, S/R-00.05\r\nAgain signal off and departure-01.35=99+3=102\" extra", "CLE NRT AT PRE\r\nLoco 33733/LDH+33626/CNB (Dead)\r\nCTO at 22.15"] |  |  |  |  |
| OldLastMajorSchDone | datetime64[us] | 78,187 | 20.7580 | 11,984 | False | ["2024-01-21T00:00:00", "2024-02-25T00:00:00", "2025-03-12T00:00:00", "2023-09-20T00:00:00", "2025-01-20T00:00:00"] | 1900-01-01T00:00:00 | 2030-06-25T00:00:00 |  |  |
| OldHeavyLifting | float64 | 200,801 | 53.3109 | 3 | False | ["-1.0", "0.0", "1.0"] | -1.0 | 1.0 | -0.940754 |  |
| OldTypeOfRepair | float64 | 200,906 | 53.3388 | 3 | False | ["-1.0", "0.0", "1.0"] | -1.0 | 1.0 | -0.934835 |  |
| OldRemoveSerive | float64 | 188,683 | 50.0937 | 3 | False | ["-1.0", "0.0", "1.0"] | -1.0 | 1.0 | -0.910473 |  |
| OldDetectedAt | float64 | 200,894 | 53.3356 | 3 | False | ["2.0", "-1.0", "1.0"] | -1.0 | 2.0 | 1.886662 |  |
| OldWithdrawServicesAt | str | 188,683 | 50.0937 | 1,109 | False | ["", "UMB", "EKI", "JNU", "BE"] |  |  |  |  |
| OldWthdrawTime | str | 188,683 | 50.0937 | 1,911 | False | ["", "11/04/2024 19:36", "04/07/2024 08:25", "22/05/2025 00:00", "19/06/2025 13:26"] |  |  |  |  |
| OldLocoUnit | float64 | 188,580 | 50.0664 | 2 | False | ["1.0", "2.0"] | 1.0 | 2.0 | 1.014621 |  |
| OldLastMinorSchDate | datetime64[us] | 52,408 | 13.9139 | 25,368 | False | ["2025-08-06T00:00:00", "2025-09-12T01:30:00", "2025-06-08T20:39:00", "2024-12-02T08:00:00", "2024-01-08T12:12:00"] | 1900-01-01T00:00:00 | 2026-07-23T13:45:00 |  |  |
| OldWagon1LastMajorSchAt | str | 200,906 | 53.3388 | 2 | False | ["", "LastMajorSchAt"] |  |  |  |  |
| OldWagon1LastMinorSchAt | str | 200,906 | 53.3388 | 2 | False | ["", "LastMinorSchAt"] |  |  |  |  |
| OldWagon2LastMajorSch | str | 200,906 | 53.3388 | 1 | False | [""] |  |  |  |  |
| OldWagon2LastMajorSchDate | datetime64[us] | 200,906 | 53.3388 | 1 | False | ["1900-01-01T00:00:00"] | 1900-01-01T00:00:00 | 1900-01-01T00:00:00 |  |  |
| OldWagon2LastMajorSchAt | str | 200,906 | 53.3388 | 1 | False | [""] |  |  |  |  |
| OldWagon2LastMinorSch | str | 200,906 | 53.3388 | 1 | False | [""] |  |  |  |  |
| OldWagon2LastMinorSchDoneOn | datetime64[us] | 200,906 | 53.3388 | 1 | False | ["1900-01-01T00:00:00"] | 1900-01-01T00:00:00 | 1900-01-01T00:00:00 |  |  |
| OldWagon2LastMinorSchDoneAt | str | 200,906 | 53.3388 | 1 | False | [""] |  |  |  |  |
| OldMainEqPosition | str | 217,340 | 57.7019 | 1,487 | False | ["-1", "1588", "0", "1236", "5674"] |  |  |  |  |
| OldMainEqNumber | str | 217,338 | 57.7014 | 9,341 | False | ["", "NELA0-29095030", "T1811300-P101", "AM0432", "101"] |  |  |  |  |
| OldMainEqOHDetail | str | 217,340 | 57.7019 | 1,096 | False | ["", "05/01/2024", "01/01/1900", "19/08/2023", "05/08/2024"] |  |  |  |  |
| OldSubEqPosition | str | 217,340 | 57.7019 | 479 | False | ["0", "-1", "3662", "1262", "4981"] |  |  |  |  |
| OldSubEqNumber | str | 217,340 | 57.7019 | 889 | False | ["", "TKD283", "230295150010", "K3302", "7486"] |  |  |  |  |
| OldSubEqOHDetails | str | 217,340 | 57.7019 | 170 | False | ["", "10/12/2008", "27/04/2024", "01/01/1900", "26/08/2024"] |  |  |  |  |
| OldFailureCauseInvestigated | float64 | 180,866 | 48.0184 | 43 | False | ["54.0", "61.0", "32.0", "-1.0", "28.0"] | -1.0 | 66.0 | 25.273257 |  |
| OldSectionKm | str | 188,682 | 50.0935 | 1,753 | False | ["", "AT BJ", "AZA", "ANVT", "HW YARD"] |  |  |  |  |
| OldLoad | str | 188,591 | 50.0693 | 1,327 | False | ["", "1350", "Load - 20 LHB Coaches", "5050", "3704"] |  |  |  |  |
| OldReportedDiv | float64 | 188,675 | 50.0916 | 2 | False | ["0.0", "1.0"] | 0.0 | 1.0 | 0.028289 |  |
| OldReportedHQ | float64 | 188,669 | 50.0900 | 2 | False | ["0.0", "1.0"] | 0.0 | 1.0 | 0.048619 |  |
| OldReportedIR | float64 | 188,682 | 50.0935 | 2 | False | ["0.0", "1.0"] | 0.0 | 1.0 | 0.00192 |  |
| OldReportedER | float64 | 188,682 | 50.0935 | 2 | False | ["0.0", "1.0"] | 0.0 | 1.0 | 0.001894 |  |
| OldLastMajorSch | float64 | 78,131 | 20.7431 | 16 | False | ["10.0", "12.0", "14.0", "-1.0", "16.0"] | -1.0 | 70.0 | 9.369492 |  |
| OldLastMinorSch | float64 | 52,366 | 13.9027 | 22 | False | ["6.0", "8.0", "5.0", "-1.0", "18.0"] | -1.0 | 77.0 | 5.852791 |  |
| OldLastMajorSchAt | float64 | 78,195 | 20.7601 | 87 | False | ["21.0", "20.0", "23.0", "171.0", "293.0"] | -1.0 | 403.0 | 64.088989 |  |
| OldLastMinorSchAt | float64 | 52,471 | 13.9306 | 122 | False | ["22.0", "21.0", "20.0", "23.0", "10.0"] | -1.0 | 403.0 | 85.58986 |  |
| OldLastTISchDate | datetime64[us] | 188,677 | 50.0921 | 1,358 | False | ["1900-01-01T00:00:00", "2024-04-03T00:00:00", "2024-09-22T00:00:00", "2024-05-08T00:00:00", "2024-10-29T00:00:00"] | 1900-01-01T00:00:00 | 2026-07-10T00:00:00 |  |  |
| OldLastTISchAt | float64 | 188,683 | 50.0937 | 125 | False | ["-1.0", "55.0", "15.0", "37.0", "96.0"] | -1.0 | 417.0 | 4.003607 |  |
| OldGrediantPercentage | str | 188,683 | 50.0937 | 62 | False | ["", "1/100", "UP", "0", "1/200"] |  |  |  |  |
| OldInspectorId | str | 200,906 | 53.3388 | 31 | False | ["", "SH. VISHWANATH DUBEY", "PREMKANT", "SEE0041", "PGT0023"] |  |  |  |  |
| OldCrew1 | float64 | 375,149 | 99.5988 | 867 | False | ["46681.0", "47796.0", "46491.0", "47569.0", "47755.0"] | 6223.0 | 47987.0 | 43965.350099 |  |
| OldCrew2 | float64 | 376,042 | 99.8359 | 369 | False | ["47201.0", "46882.0", "44344.0", "44348.0", "47001.0"] | 6224.0 | 47940.0 | 42740.2589 |  |
| OldCrewMisMgmt | float64 | 7,403 | 1.9654 | 6 | False | ["1.0", "13.0", "3.0", "2.0", "4.0"] | 1.0 | 13.0 | 6.121633 |  |
| OldIssuedDivision | float64 | 200,906 | 53.3388 | 2 | False | ["-1.0", "55.0"] | -1.0 | 55.0 | -0.999681 |  |
| OldIssuedRailways | float64 | 200,906 | 53.3388 | 2 | False | ["-1.0", "14.0"] | -1.0 | 14.0 | -0.999915 |  |
| OldBreakPowerPer | float64 | 200,906 | 53.3388 | 1 | False | ["0.0"] | 0.0 | 0.0 | 0.0 |  |
| OldRaketype | float64 | 200,906 | 53.3388 | 2 | False | ["-1.0", "1.0"] | -1.0 | 1.0 | -0.999989 |  |
| OldAvoidable | float64 | 200,801 | 53.3109 | 3 | False | ["-1.0", "1.0", "0.0"] | -1.0 | 1.0 | -0.921409 |  |
| OldNoofWagons | float64 | 188,683 | 50.0937 | 64 | False | ["0.0", "22.0", "18.0", "46.0", "43.0"] | 0.0 | 1400.0 | 1.179309 |  |
| OldNoOfUnits | float64 | 188,683 | 50.0937 | 70 | False | ["0.0", "2.0", "1.0", "43.0", "44.0"] | 0.0 | 3465.0 | 0.827277 |  |
| OldPositionFromEngin | str | 200,906 | 53.3388 | 2 | False | ["", "7th - 8th"] |  |  |  |  |
| OldPositionFromGaurd | str | 200,906 | 53.3388 | 2 | False | ["", "35th"] |  |  |  |  |
| OldMainEqMake | float64 | 348,944 | 92.6416 | 354 | False | ["140.0", "406.0", "41.0", "2.0", "254.0"] | 1.0 | 2011.0 | 237.751335 |  |
| OldSubEqMake | float64 | 375,464 | 99.6825 | 106 | False | ["78.0", "315.0", "64.0", "254.0", "277.0"] | 1.0 | 1984.0 | 340.004181 |  |
| OldPartingReason | float64 | 200,906 | 53.3388 | 2 | False | ["-1.0", "3.0"] | -1.0 | 3.0 | -0.999977 |  |
| OldCrewHQ | float64 | 200,827 | 53.3178 | 69 | False | ["-1.0", "97.0", "125.0", "9.0", "154.0"] | -1.0 | 19944.0 | -0.030739 |  |
| OldITEMRECON | float64 | 200,906 | 53.3388 | 2 | False | ["0.0", "1.0"] | 0.0 | 1.0 | 0.001724 |  |
| OldUNSCHEDULE | float64 | 200,906 | 53.3388 | 2 | False | ["0.0", "1.0"] | 0.0 | 1.0 | 0.004626 |  |
| OldUNSCHWORK | float64 | 200,906 | 53.3388 | 2 | False | ["0.0", "1.0"] | 0.0 | 1.0 | 0.000922 |  |
| OldREMEDIAL | float64 | 200,906 | 53.3388 | 3 | False | ["-1.0", "1.0", "0.0"] | -1.0 | 1.0 | -0.836055 |  |
| OldREMARKS | str | 199,627 | 52.9993 | 22,447 | False | ["", "In Cab?1, the ALP side sander was found not functioning and the LP side sandbox pipe was disconnected. TXR staff attended the issue, reconnected the LP side sandbox pipe, and upon inspection discovered a nozzle jam on the ALP side. The nozzle was cleaned, after which the sander was tested and found to be working.", "Loco checked at NDLS on 09.11.25, In DDS \r\n\"FLG1: Lifesign from BUR3 missing\r\nFLG1: Auxiliary Converter3 off\r\nSTB1: MCB of CP1 open\" message was found logged. BUR3 was isolated and found BUR3 R phase WRE defective.", "Traffic/wrongly logged", "LOCO CHECKED AT GHUWATI TI SHED AND FOUND  CP2 intercooler pipe damage causing air leakage resulting in time to time MR pressure drop.Cp-2 inter coller cooling pipe broken\r\nON DT 11/7/24 MR PRESSURE DROP . LOCO CHECKED AT NGC TRIP SHED FOUND CP 2 INTERCOOLER PIPE DAMAGED CAUSING AIR LEAKAGE RESULTING IN TIME TO TIME MR PRESSURE DROP .There were several messages of FLG:0092-ACP/Train part were logged in DDS."] |  |  |  |  |
| OldREMEDIALAction | str | 200,794 | 53.3091 | 4,911 | False | ["", "New CP was provided", "Same loco worked the train and no attention was needed to CBC coupler.", "All Side filter and OCB cleaning done on date 26/04/2025", "Traffic wrongly logged"] |  |  |  |  |
| OldActionPlan | str | 200,786 | 53.3070 | 9,481 | False | ["", "Contract is being planned for provision of gaurd on the aftercooler assembly of CP.", "The working of both cab CBC and TSC couplings is checked in the shed during every schedule (TI, IA, IB, IC). The CBC operating handle modification was carried out during the POH schedule at POH /KGP.", "1-Clean the all side filters in every schedule as per SMI-286 and measure the air delivery as per SMI-255 if found air flow less than reclean its.\r\n2-Clean the both radiator as per SMI-287 and measure the air delivery as per SMI-255 if found less than reclean it.", "Traffic wrongly logged"] |  |  |  |  |
| OldRBEq | object | 376,660 | 100.0000 | 0 | False | [] |  |  |  |  |
| OldMovementRegister | float64 | 278,064 | 73.8236 | 33,466 | False | ["1252262.0", "775560.0", "1244931.0", "1248564.0", "878996.0"] | 157734.0 | 1463935.0 | 1173101.948071 |  |
| OldShedSection | float64 | 200,803 | 53.3115 | 797 | False | ["-2.0", "-1.0", "65.0", "735.0", "739.0"] | -2.0 | 4026.0 | 295.051132 |  |
| OldEqDoC | datetime64[us] | 200,903 | 53.3380 | 2,862 | False | ["1900-01-01T00:00:00", "2010-02-05T00:00:00", "2023-04-13T00:00:00", "2016-10-12T00:00:00", "2019-01-20T00:00:00"] | 1900-01-01T00:00:00 | 2026-10-04T00:00:00 |  |  |
| OldEqLastProvidingDate | datetime64[us] | 200,906 | 53.3388 | 2,223 | False | ["1900-01-01T00:00:00", "2020-11-06T00:00:00", "2020-12-03T00:00:00", "2021-10-01T00:00:00", "2019-04-12T00:00:00"] | 1900-01-01T00:00:00 | 2071-04-04T00:00:00 |  |  |
| OldSubEqDoC | datetime64[us] | 217,339 | 57.7016 | 300 | False | ["1900-01-01T00:00:00", "2016-10-12T00:00:00", "2023-07-04T00:00:00", "2024-02-10T00:00:00", "2021-01-10T00:00:00"] | 1900-01-01T00:00:00 | 2026-06-01T00:00:00 |  |  |
| OldSubEqLastProvidingDate | datetime64[us] | 217,340 | 57.7019 | 401 | False | ["1900-01-01T00:00:00", "2023-07-04T00:00:00", "2024-02-10T00:00:00", "2020-11-27T00:00:00", "2020-09-05T00:00:00"] | 1900-01-01T00:00:00 | 2026-07-07T00:00:00 |  |  |
| OldHistory | float64 | 38,089 | 10.1123 | 3 | False | ["0.0", "1.0", "2.0"] | 0.0 | 2.0 | 0.49312 |  |
| OldOnlineAttLocation | float64 | 357,796 | 94.9918 | 161 | False | ["0.0", "91.0", "90.0", "92.0", "-1.0"] | -1.0 | 404.0 | 11.841179 |  |
| OldMovementflag | object | 376,660 | 100.0000 | 0 | False | [] |  |  |  |  |
| OldTrainNo | str | 188,513 | 50.0486 | 7,588 | False | ["", "NPSB-E-BOXN", "15658", "04652", "15211"] |  |  |  |  |
| OldFailCode | float64 | 202,826 | 53.8486 | 2,609 | False | ["4077.0", "788.0", "3675.0", "5182.0", "4154.0"] | -1.0 | 10154.0 | 3919.130354 |  |
| OldInspLastFPDate | str | 200,906 | 53.3388 | 3 | False | ["", "15/10/2023", "11.08.2023"] |  |  |  |  |
| OldMinorEq | float64 | 200,906 | 53.3388 | 148 | False | ["0.0", "-1.0", "192.0", "652.0", "391.0"] | -1.0 | 843.0 | 1.382062 |  |
| OldMinorEqMake | float64 | 376,640 | 99.9947 | 13 | False | ["21.0", "1624.0", "293.0", "178.0", "132.0"] | 0.0 | 1624.0 | 220.8 |  |
| OldMinorEqNumber | str | 200,906 | 53.3388 | 57 | False | ["", "016", "3108", "22363/2", "401A"] |  |  |  |  |
| OldMinorEqOHDetail | str | 200,906 | 53.3388 | 26 | False | ["", "09/09/2022", "24/08/2024", "18/04/2023", "17/05/2022"] |  |  |  |  |
| OldMinorEqPosition | str | 200,906 | 53.3388 | 2 | False | ["", "0"] |  |  |  |  |
| OldCoEq | float64 | 200,906 | 53.3388 | 1 | False | ["0.0"] | 0.0 | 0.0 | 0.0 |  |
| OldCoEqMake | float64 | 200,906 | 53.3388 | 1 | False | ["0.0"] | 0.0 | 0.0 | 0.0 |  |
| OldCoEqNumber | str | 200,906 | 53.3388 | 1 | False | [""] |  |  |  |  |
| OldCoEqOHDetail | str | 200,906 | 53.3388 | 1 | False | [""] |  |  |  |  |
| OldCoEqPosition | str | 200,906 | 53.3388 | 1 | False | [""] |  |  |  |  |
| oldmor | object | 376,660 | 100.0000 | 0 | False | [] |  |  |  |  |
| oldmor2 | object | 376,660 | 100.0000 | 0 | False | [] |  |  |  |  |
| OldOtherEq | str | 200,697 | 53.2833 | 4,862 | False | ["", "MCB -100 25A Make-ABB Typ-e - S203 Provided on dt.27.02.24", "CP intercooler was damaged due to external hitting.", "BT Propulsion loco with software ver. 1.4.1.4 on dt.29.03.25.", "First Schedule at ELS/LDH (IA schedule) was done on date 2/01/25 At that time Air delivery was found ok (as per aux Section measurement ).But Both TMB air blowing was done precautionary"] |  |  |  |  |
| OldDeleted | int64 | 0 | 0.0000 | 2 | False | ["0", "1"] | 0 | 1 | 0.01123 |  |
| OldLogBookEntry | float64 | 200,906 | 53.3388 | 3 | False | ["-1.0", "0.0", "1.0"] | -1.0 | 1.0 | -0.926579 |  |
| OldLogBookDetails | str | 200,836 | 53.3202 | 1,843 | False | ["", "Aux conv-2 & MRB-2 MCB 54.1/2 was already isolate & trip off.between SK-GLTA all 3 conver isolated & Main power off.suspected earth fault in MRB-2 so MCB 54.1/2 trip off again and again & also con.aux 1,2,3 isolated  & main power off so found trouble suspected MRB-2 defective .Loco dead to home shed.", "It is worth to note that TM-5 was isolated due to pinion cut at BRC since 29.03.2024\r\nand loco was given fit with five TM’s to home shed and instead of directing the loco to home\r\nshed;", "VCB STUCK IN OFF POSITION DUE TO VCB PRV BROKEN (Festo make) PRV replaced with new one. Loco checked and attended at TKD trip shed found normal.", "Traction not coming from cab-2."] |  |  |  |  |
| OldCurrDivision | float64 | 319,623 | 84.8572 | 111 | False | ["144.0", "121.0", "126.0", "125.0", "99.0"] | -1.0 | 271.0 | 134.667812 |  |
| OldBaseShed | float64 | 376,340 | 99.9150 | 42 | False | ["340.0", "4.0", "38.0", "325.0", "247.0"] | 2.0 | 340.0 | 196.93125 |  |
| eLoco | float64 | 376,633 | 99.9928 | 27 | False | ["5785.0", "1778.0", "7750.0", "1549.0", "5967.0"] | 357.0 | 9670.0 | 5572.62963 |  |
| eLocoEquipt | str | 376,633 | 99.9928 | 18 | False | ["Bogie & its Mech. equip.", "Miscellaneous", "VCD/ TPWS ", "Traction converter GTO (SR)", "Battery"] |  |  |  |  |
| eLococrewsubclass | str | 376,659 | 99.9997 | 1 | False | ["Bad troubleshooting"] |  |  |  |  |
| OldMinorEqDoC | datetime64[us] | 200,907 | 53.3391 | 8 | False | ["1900-01-01T00:00:00", "2023-03-31T00:00:00", "2022-07-03T00:00:00", "2022-05-13T00:00:00", "2019-04-01T00:00:00"] | 1900-01-01T00:00:00 | 2023-03-31T00:00:00 |  |  |
| OldMinorEqLastProvidingDate | datetime64[us] | 200,907 | 53.3391 | 12 | False | ["1900-01-01T00:00:00", "2023-01-09T00:00:00", "2023-01-05T00:00:00", "2023-03-31T00:00:00", "2022-07-03T00:00:00"] | 1900-01-01T00:00:00 | 2023-08-15T00:00:00 |  |  |
| OldClosedOn | object | 376,660 | 100.0000 | 0 | False | [] |  |  |  |  |
| OldLocoBaseLocation | object | 376,660 | 100.0000 | 0 | False | [] |  |  |  |  |
| StaffId | str | 200,915 | 53.3412 | 44 | False | ["0", "46221", "-1", "25106", "39440"] |  |  |  |  |
| OldWarranty | float64 | 200,915 | 53.3412 | 3 | False | ["-1.0", "0.0", "1.0"] | -1.0 | 1.0 | -0.599016 |  |
| OldWarrantyReference | str | 200,936 | 53.3468 | 209 | False | ["", "006601-24-00437", "NCR/CNB/4801", "NCR-20250500012 ON DT-19-05-25", "AMC"] |  |  |  |  |
| OldLineFailureRemarks | str | 361,089 | 95.8660 | 31 | False | ["ASSET FAILURE", "13", "", "2", "Loco was failed before commissioning at Shed. During Shed investigation it was found that Snubber diode of Thermal relay (Pos. 211) was found defective which was causing tripping of commissioning ckt. it was replaced & loco become normal."] |  |  |  |  |
| icmsaflid | str | 18,446 | 4.8973 | 130,298 | False | ["5256166", "26907852", "5174603", "5159051", "5122237"] |  |  |  |  |
| icmsaflfailurecode | str | 18,383 | 4.8805 | 34 | False | ["ELEC_L", "DELC", "ELEC_LOCO", "IELC", "WAGON"] |  |  |  |  |
| icmsaflfailuresubcode | str | 18,443 | 4.8965 | 89 | False | ["ECRW", "OTH", "EGPSDEF", "DSDF", "DSRC"] |  |  |  |  |
| icmsFlag | str | 18,446 | 4.8973 | 2 | False | ["ICMS", "PUNC"] |  |  |  |  |
| oldminorsection | str | 70,230 | 18.6455 | 11,793 | False | ["PURI", "UDN", "VSKP", "BBS", "GNPR"] |  |  |  |  |
| oldnextdueschmsmid | float64 | 74,221 | 19.7050 | 47,068 | False | ["743548.0", "880360.0", "880359.0", "880357.0", "880354.0"] | 4795.0 | 6955224.0 | 4140863.734055 |  |
| OldLocoCondition | str | 201,884 | 53.5985 | 3 | False | ["1", "-1", "0"] |  |  |  |  |
| OldZonalRemark | str | 161,742 | 42.9411 | 25,694 | False | ["MCB down, As per next loco working link, At mean time case is lodged wrongly on loco/crew account", "System: Analysis Not Required", "Excess time taken due to Home signal & Gate signal late taken off at JRW, signal checked at GHN starter Signal and passed via loop line at JMT, VDS, JSME and SR at NPZ & LHB.", "Wrong logging", "For Crew"] |  |  |  |  |
| oldDateOccuranceEnd | datetime64[us] | 55,276 | 14.6753 | 75,803 | False | ["2025-11-06T09:03:00", "1900-01-01T00:00:00", "2025-09-14T00:48:00", "2025-08-10T00:01:00", "2022-05-30T23:30:00"] | 1900-01-01T00:00:00 | 2026-07-24T11:35:00 |  |  |
| OldRDSORemark | str | 375,648 | 99.7313 | 160 | False | ["As per request email of SER/HQ on 22.09.2025, the case is reopened for updating.", "As per request email dated 11.06.2025 to reopen the case by LPC/KRCL for TLC/KAWR, it is reopened.", "As per request of WR/HQ, the case is reopened for updating.", "As per request of DLS/RTM/WR on 25.11.2025, the case is reopened for updating.", "As per request of SCR/HQ Official on 04.12.2025, the case is reopened for updating"] |  |  |  |  |
| slamdatetime | datetime64[us] | 65,062 | 17.2734 | 87,242 | False | ["2025-11-06T04:52:45.940000", "2025-09-30T02:21:44.507000", "2025-09-22T13:35:43.263000", "2025-09-13T23:14:19.893000", "2025-08-25T05:02:59.967000"] | 2025-04-04T04:42:25 | 2026-07-24T15:46:12.447000 |  |  |
| Historysdatetime | datetime64[us] | 0 | 0.0000 | 198,289 | False | ["2025-12-01T15:15:54.180000", "2025-12-01T15:15:54.187000", "2025-12-01T15:15:54.840000", "2025-12-01T15:16:57.100000", "2025-12-01T15:17:11.340000"] | 2025-12-01T15:15:54.180000 | 2026-07-24T17:08:35.690000 |  |  |
