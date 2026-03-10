BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "charlie_trackeddocument" (
	"slug"	varchar(300) NOT NULL UNIQUE,
	"title"	varchar(255) NOT NULL,
	"agency"	varchar(255) NOT NULL,
	"office"	varchar(255) NOT NULL,
	"subject"	text NOT NULL,
	"file_type"	varchar(50) NOT NULL,
	"is_public"	bool NOT NULL,
	"created_at"	varchar(50) NOT NULL,
	"created_by"	varchar(100) NOT NULL,
	"validated_at"	varchar(100) NOT NULL,
	"validated_by"	varchar(100) NOT NULL,
	"document_type"	varchar(100) NOT NULL,
	"user_retention"	varchar(200) NOT NULL,
	"office_retention"	varchar(200) NOT NULL,
	"overall_days_onprocess"	varchar(200) NOT NULL,
	"document_completed_status"	bool NOT NULL,
	"details"	text NOT NULL CHECK((JSON_VALID("details") OR "details" IS NULL)),
	"created_timestamp"	datetime,
	"updated_timestamp"	datetime,
	"pdid"	integer NOT NULL,
	PRIMARY KEY("pdid" AUTOINCREMENT)
);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202415459455482-allotment-and-obligation-slip-alobs','Allotment and Obligation Slip (ALOBS)','City Government of Surigao','LEGISLATIVE SERVICES (COUNCIL 2)(Sangguniang Panlungsod)','To payment of Telephone Bill for the period of OCTOBER 2024 in the office Hon. Cacel R. Azarcon, of Sangguniang Panlungsod office, this city, as per supporting papers hereto attached.
[Amount: Php 1716.81]
[Payee: PLDT INC.]
[ALOBS ID: 0651-10-24-001]','n/a',1,'10/24/2024','Catilo,Azmar','10/24/2024 | 09:59:23 AM','Catilo,Azmar','Allotment and Obligation Slip','04 Mon/s, 04 Day/s, 23 hour/s, 13 min., & 20 sec. ','04 Mon/s, 04 Day/s, 23 hour/s, 13 min., & 20 sec. ','00 Mon/s, 05 Day/s, 04 hour/s, 03 min., & 34 sec. ',1,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1000);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202413940341988-purchase-request','PURCHASE REQUEST','City Government of Surigao','City Health Office','For orientation of new BSI''s, update on FHSIS and dengue orientation meeting

1 set EOS 4000D DSLR Camera (wifi) Original
3 sets Original Calculator mx-12 B 12 digits

amount: 49,500.00','n/a',1,'10/24/2024','Tinio,Bryant','10/24/2024 | 09:44:09 AM','Tinio,Bryant','','02 Mon/s, 13 Day/s, 23 hour/s, 46 min., & 40 sec. ','02 Mon/s, 13 Day/s, 23 hour/s, 46 min., & 40 sec. ','04 Mon/s, 01 Day/s, 00 hour/s, 52 min., & 13 sec. ',0,'{}','2026-02-25 03:44:29','2026-02-25 03:44:29',1001);
INSERT INTO "charlie_trackeddocument" VALUES ('1025202413940341989-travel-order','TRAVEL ORDER','City Government of Surigao','City Mayor''s Office','Travel order for official business to Manila for budget coordination meeting.','n/a',1,'10/25/2024','Santos, Maria','10/25/2024 | 08:00:00 AM','Santos, Maria','','','','00 Mon/s, 02 Day/s, 01 hour/s, 15 min., & 00 sec. ',1,'{}','2026-02-25 03:44:29','2026-02-25 03:44:29',1002);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202413454758746-purchase-request','PURCHASE REQUEST','City Government of Surigao','City General Services Office','8 pcs. Flood Light 100w Daylight, et.al 

Amount: 130,130.00
For use in the Installation of \"I LOVE SURIGAO\" light at City Boulevard.','n/a',1,'10/24/2024','Tinio,Ethel','10/24/2024 | 09:46:01 AM','Tinio,Ethel','','02 Mon/s, 28 Day/s, 05 hour/s, 11 min., & 59 sec. ','02 Mon/s, 28 Day/s, 05 hour/s, 11 min., & 59 sec. ','03 Mon/s, 19 Day/s, 00 hour/s, 21 min., & 12 sec. ',1,'{}','2026-02-26 06:51:00','2026-02-26 06:51:00',1003);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202414247554073-allotment-and-obligation-slip-alobs','Allotment and Obligation Slip (ALOBS)','City Government of Surigao','Surigao City Integrated Bus & Jeepney Terminal','TO PAYMENT OF INTERNET EXPENSE OF CITY INTEGRATED LABD TRANSPORT TERMINAL FOR THE PERIOD COVERED FROM OCTOBER 09, 2024 TO NOVEMBER  02, 2024 AS PER SUPPORTING PAPERS HERETO ATTACHED IN THE AMOUNT OF.....
[Amount: Php 2999.0]
[Payee: PLDT INC.]
[ALOBS ID: 0008-10-24-012]','n/a',1,'10/24/2024','Ballesteros,Maria Salome','10/24/2024 | 09:47:11 AM','Ballesteros,Maria Salome','Allotment and Obligation Slip','03 Mon/s, 27 Day/s, 23 hour/s, 14 min., & 51 sec. ','03 Mon/s, 27 Day/s, 23 hour/s, 14 min., & 51 sec. ','00 Mon/s, 05 Day/s, 05 hour/s, 31 min., & 30 sec. ',1,'{}','2026-02-26 06:51:00','2026-02-26 06:51:00',1004);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202413654723452-purchase-request','PURCHASE REQUEST','City Government of Surigao','City General Services Office','2 pcs G.I Sheet Plate #16, et.al

Amount: 32,156.50
For use in the repair of CGSO service vehicle, this city.','n/a',1,'10/24/2024','Tinio,Ethel','10/24/2024 | 09:46:03 AM','Tinio,Ethel','','02 Mon/s, 07 Day/s, 23 hour/s, 49 min., & 36 sec. ','02 Mon/s, 07 Day/s, 23 hour/s, 49 min., & 36 sec. ','02 Mon/s, 09 Day/s, 03 hour/s, 17 min., & 44 sec. ',1,'{}','2026-02-26 06:51:00','2026-02-26 06:51:00',1005);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202413749128026-purcahse-request','PURCAHSE REQUEST','City Government of Surigao','City General Services Office','2 Set Electrical Horn

Amount : 3,100.00
For use in Sea Transport, this city.','n/a',1,'10/24/2024','Tinio,Ethel','10/24/2024 | 09:46:06 AM','Tinio,Ethel','','02 Mon/s, 21 Day/s, 04 hour/s, 22 min., & 32 sec. ','02 Mon/s, 21 Day/s, 04 hour/s, 22 min., & 32 sec. ','03 Mon/s, 19 Day/s, 00 hour/s, 21 min., & 25 sec. ',1,'{}','2026-02-26 06:51:00','2026-02-26 06:51:00',1006);
INSERT INTO "charlie_trackeddocument" VALUES ('102420241395511418-purchase-request','PURCHASE REQUEST','City Government of Surigao','City General Services Office','10 rolls Duplex Wire #16, et.al

Amount: 119,750.00
For use in replacement of busted Capiz Shell Balls Light at the Luneta Park, this city.','n/a',1,'10/24/2024','Tinio,Ethel','10/24/2024 | 09:46:08 AM','Tinio,Ethel','','02 Mon/s, 00 Day/s, 03 hour/s, 53 min., & 30 sec. ','02 Mon/s, 00 Day/s, 03 hour/s, 53 min., & 30 sec. ','03 Mon/s, 19 Day/s, 03 hour/s, 40 min., & 59 sec. ',1,'{}','2026-03-03 05:45:16','2026-03-03 05:45:16',1007);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202414128926318-purchase-request','PURCHASE REQUEST','City Government of Surigao','City General Services Office','50 Pcs Electrical Tape, et.al

Amount: 152,185.00
For use in the Installation of Tree Light at the Luneta Park, this city.','n/a',1,'10/24/2024','Tinio,Ethel','10/24/2024 | 09:46:12 AM','Tinio,Ethel','','02 Mon/s, 29 Day/s, 03 hour/s, 19 min., & 15 sec. ','02 Mon/s, 29 Day/s, 03 hour/s, 19 min., & 15 sec. ','02 Mon/s, 09 Day/s, 03 hour/s, 17 min., & 58 sec. ',1,'{}','2026-03-03 05:45:17','2026-03-03 05:45:17',1008);
INSERT INTO "charlie_trackeddocument" VALUES ('102420241444814558-allotment-and-obligation-slip-alobs','Allotment and Obligation Slip (ALOBS)','City Government of Surigao','Surigao City Integrated Bus & Jeepney Terminal','TO PAYMENT OF 2 TRIPS LUMPSUM SERVICES for DISLODGING SEPTIC TANK  OF CITY INTEGRATED LAND TRANSPORT TERMINAL AS PER SUPPORTING PAPERS HERETO ATTACHED IN THE AMOUNT OF......
[Amount: Php 17680.0]
[Payee: R. S YUIPCO DEVELOPMENT CORPORATION]
[ALOBS ID: 0009-10-24-012]','n/a',1,'10/24/2024','Ballesteros,Maria Salome','10/24/2024 | 09:49:12 AM','Ballesteros,Maria Salome','Allotment and Obligation Slip','03 Mon/s, 14 Day/s, 01 hour/s, 26 min., & 00 sec. ','03 Mon/s, 14 Day/s, 01 hour/s, 26 min., & 00 sec. ','00 Mon/s, 26 Day/s, 02 hour/s, 16 min., & 40 sec. ',1,'{}','2026-03-03 05:45:17','2026-03-03 05:45:17',1009);
INSERT INTO "charlie_trackeddocument" VALUES ('102420241455358419-allotment-and-obligation-slip-alobs','Allotment and Obligation Slip (ALOBS)','City Government of Surigao','Surigao City Integrated Bus & Jeepney Terminal','TO PAYMENT OF OFFICE EQUIPMENT (10 UNITS SOLAR STREET LIGHT)  OF CITY INTEGRATED LAND TRANSPORT TERMINAL AS PER SUPPORTING PAPERS HERETO ATTACHED IN THE AMOUNT OF..... 
[Amount: Php 21000.0]
[Payee: VOCOM ENTERPRISES]
[ALOBS ID: 0010-10-24-012]','n/a',1,'10/24/2024','Ballesteros,Maria Salome','10/24/2024 | 09:50:16 AM','Ballesteros,Maria Salome','Allotment and Obligation Slip','03 Mon/s, 14 Day/s, 01 hour/s, 24 min., & 13 sec. ','03 Mon/s, 14 Day/s, 01 hour/s, 24 min., & 13 sec. ','00 Mon/s, 26 Day/s, 02 hour/s, 16 min., & 14 sec. ',1,'{}','2026-03-03 05:45:17','2026-03-03 05:45:17',1010);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202414722885742-fuel-withdrawal-oct-24-2024-isuzu-ambulance','Fuel Withdrawal ( Oct. 24, 2024 - Isuzu (Ambulance))','City Government of Surigao','City Disaster Risk Reduction Management Office','Fuel Withdrawal ( Oct. 24, 2024 - Isuzu (Ambulance)) - Balance 770 liters','n/a',1,'10/24/2024','Ma,Wingpin','10/24/2024 | 09:51:49 AM','Ma,Wingpin','','01 Mon/s, 03 Day/s, 01 hour/s, 08 min., & 25 sec. ','01 Mon/s, 03 Day/s, 01 hour/s, 08 min., & 25 sec. ','04 Mon/s, 10 Day/s, 03 hour/s, 22 min., & 46 sec. ',0,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1011);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202412238719916-variation-order','VARIATION ORDER','City Government of Surigao','Construction(City Engineering Office)','Proposed Variation Order No. 1 for the project: ROAD CONCRETING OF FILE-PINAYPAYAN-BRAZIL ROAD, BRGY. MAT-I, SURIGAO CITY under contract with EYT CONSTRUCTION.','n/a',1,'10/24/2024','Ancla,Marie Magdalene','10/24/2024 | 09:35:58 AM','Ancla,Marie Magdalene','','04 Mon/s, 05 Day/s, 03 hour/s, 16 min., & 17 sec. ','04 Mon/s, 08 Day/s, 22 hour/s, 31 min., & 02 sec. ','04 Mon/s, 10 Day/s, 03 hour/s, 15 min., & 59 sec. ',0,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1012);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202412359906601-variation-order','VARIATION ORDER','City Government of Surigao','Construction(City Engineering Office)','Proposed Variation Order No. 1 for the project: CONST. OF WATER SYSTEM, PHASE II, BRGY. BUENAVISTA, SURIGAO CITY under contract with EYT CONSTRUCTION.','n/a',1,'10/24/2024','Ancla,Marie Magdalene','10/24/2024 | 09:36:03 AM','Ancla,Marie Magdalene','','04 Mon/s, 05 Day/s, 03 hour/s, 12 min., & 00 sec. ','04 Mon/s, 08 Day/s, 22 hour/s, 28 min., & 23 sec. ','04 Mon/s, 10 Day/s, 03 hour/s, 15 min., & 16 sec. ',0,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1013);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202412511384974-variation-order','VARIATION ORDER','City Government of Surigao','Construction(City Engineering Office)','Proposed Variation Order No. 1 for the project: UPGRADING OF BHS, BRGY. SABANG, SURIGAO CITY under contract with ROMZ BUILDERS.','n/a',1,'10/24/2024','Ancla,Marie Magdalene','10/24/2024 | 09:36:05 AM','Ancla,Marie Magdalene','','04 Mon/s, 05 Day/s, 02 hour/s, 57 min., & 55 sec. ','04 Mon/s, 05 Day/s, 03 hour/s, 23 min., & 28 sec. ','04 Mon/s, 10 Day/s, 03 hour/s, 16 min., & 32 sec. ',0,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1014);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202412626677697-variation-order','VARIATION ORDER','City Government of Surigao','Construction(City Engineering Office)','Proposed Variation Order No. 1 for the project: REHABILITATION OF HEALTH CENTER, BRGY. SUGBAY, SURIGAO CITY under contract with VBB CONSTRUCTION.','n/a',1,'10/24/2024','Ancla,Marie Magdalene','10/24/2024 | 09:36:08 AM','Ancla,Marie Magdalene','','04 Mon/s, 05 Day/s, 02 hour/s, 56 min., & 20 sec. ','04 Mon/s, 08 Day/s, 22 hour/s, 33 min., & 53 sec. ','04 Mon/s, 10 Day/s, 03 hour/s, 16 min., & 35 sec. ',0,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1015);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202412841586641-variation-order-w-attach-as-built-plan','VARIATION ORDER w/ attach AS BUILT PLAN','City Government of Surigao','Construction(City Engineering Office)','Proposed Variation Order No. 2 for the project: CONSTRUCTION OF MINI-PUBLIC MARKET, BRGY. TAFT, SURIGAO CITY under contract with ALGAMON CONSTRUCTION.','n/a',1,'10/24/2024','Ancla,Marie Magdalene','10/24/2024 | 09:36:11 AM','Ancla,Marie Magdalene','','04 Mon/s, 05 Day/s, 02 hour/s, 28 min., & 34 sec. ','04 Mon/s, 08 Day/s, 22 hour/s, 39 min., & 22 sec. ','03 Mon/s, 20 Day/s, 06 hour/s, 23 min., & 10 sec. ',1,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1016);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202412951995750-variation-order','VARIATION ORDER','City Government of Surigao','Construction(City Engineering Office)','Proposed Variation Order No. 1 for the project: CONSTRUCTION OF BARANGAY HALL, BRGY. SAN ROQUE, SURIGAO CITY, under contract with EYT CONSTRUCTION.','n/a',1,'10/24/2024','Ancla,Marie Magdalene','10/24/2024 | 09:36:13 AM','Ancla,Marie Magdalene','','04 Mon/s, 05 Day/s, 02 hour/s, 27 min., & 15 sec. ','04 Mon/s, 08 Day/s, 22 hour/s, 27 min., & 19 sec. ','04 Mon/s, 10 Day/s, 03 hour/s, 16 min., & 33 sec. ',0,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1017);
INSERT INTO "charlie_trackeddocument" VALUES ('1024202413119394950-variation-order','VARIATION ORDER','City Government of Surigao','Construction(City Engineering Office)','Proposed Variation Order No. 1 for the project: CONCRETING OF MAIN ACCESS ROAD TO SLF, BRGY. LUNA, SRUIGAO CITY under contract with AJP BUILDERS AND SUPPLY.','n/a',1,'10/24/2024','Ancla,Marie Magdalene','10/24/2024 | 09:36:16 AM','Ancla,Marie Magdalene','','04 Mon/s, 05 Day/s, 02 hour/s, 26 min., & 09 sec. ','04 Mon/s, 05 Day/s, 03 hour/s, 20 min., & 24 sec. ','04 Mon/s, 10 Day/s, 03 hour/s, 16 min., & 29 sec. ',0,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1018);
INSERT INTO "charlie_trackeddocument" VALUES ('102420241572593157-purchase-order','Purchase Order','City Government of Surigao','City Social Welfare and Development Office','2 pcs. Signal light front LH & RH bulb, 2 pcs. Headlights 12 volts LH & RH bulb, 2 pcs. Tail light left & right bulb, 1 pc. Clutch cable for Suzuki (double cab 12 volts), 1 pc. Cable Accelerator for Suzuki (double cab 12 volts), & etc. amounting to Php 27, 720.00','n/a',1,'10/24/2024','Plandano,Amie','10/24/2024 | 10:01:34 AM','Plandano,Amie','','04 Mon/s, 10 Day/s, 02 hour/s, 42 min., & 04 sec. ','04 Mon/s, 10 Day/s, 02 hour/s, 42 min., & 04 sec. ','04 Mon/s, 10 Day/s, 03 hour/s, 16 min., & 10 sec. ',0,'{}','2026-03-03 05:27:29','2026-03-03 05:27:29',1019);
COMMIT;
