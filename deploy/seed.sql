
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
DROP TABLE IF EXISTS `age`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `age` (
  `ageID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ageName` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`ageID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `agetype`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `agetype` (
  `ageID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ageName` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `animalTypeID` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `animalID` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`ageID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `animaltype`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `animaltype` (
  `animalTypeID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalName` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`animalTypeID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `breedingstock`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `breedingstock` (
  `animalID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalName` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalTypeID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`animalID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `collecteddata`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `collecteddata` (
  `formID` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalTypeID` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `animalID` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `speciesID` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ageID` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `genderID` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dataCount` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `district`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `district` (
  `stateID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `districtID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `districtName` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`stateID`,`districtID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `gender`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `gender` (
  `genderID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `genderName` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`genderID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `largeanimals`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `largeanimals` (
  `animalID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalName` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalTypeID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`animalID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `largespecies`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `largespecies` (
  `speciesID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `speciesName` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`speciesID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `livestock`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `livestock` (
  `animalID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalName` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalTypeID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`animalID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `livestockspecies`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `livestockspecies` (
  `speciesID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `speciesName` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `animalID` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`speciesID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `personcv`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `personcv` (
  `formID` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `userId` int DEFAULT NULL,
  `stateID` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `districtID` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `townshipID` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `QVID` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `WardName` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `householdNo` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `gender` varchar(15) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `eduStatus` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `phoneNo` varchar(15) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `age` int NOT NULL,
  `interviewDate` date NOT NULL,
  `headName` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `headEduStatus` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `headGender` varchar(15) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `headPhoneNo` varchar(15) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `headAge` int NOT NULL,
  `Interviewer` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `interviewerPhoneNo` varchar(15) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` tinyint NOT NULL DEFAULT '0',
  PRIMARY KEY (`formID`),
  KEY `fk_personcv_user` (`userId`),
  CONSTRAINT `fk_personcv_user` FOREIGN KEY (`userId`) REFERENCES `user` (`userID`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `ck_personcv_status` CHECK ((`status` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `qv`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `qv` (
  `stateID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `districtID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `townshipID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `QVID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `QVName` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`stateID`,`districtID`,`townshipID`,`QVID`),
  KEY `qvindex` (`stateID`,`districtID`,`townshipID`,`QVID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `state`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `state` (
  `stateID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `stateName` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`stateID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `township`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `township` (
  `stateID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `districtID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `townshipID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `townshipName` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`stateID`,`districtID`,`townshipID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user` (
  `userID` int NOT NULL AUTO_INCREMENT,
  `userName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `userRole` int NOT NULL,
  `loginName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `stateID` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `districtID` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `townshipID` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `QVID` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` int DEFAULT '1',
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`userID`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `userrole`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `userrole` (
  `roleId` int NOT NULL,
  `roleName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`roleId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('admin','staff') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `younganimals`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `younganimals` (
  `animalID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalName` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalTypeID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`animalID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `youngspecies`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `youngspecies` (
  `speciesID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `speciesName` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `animalID` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`speciesID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;


-- Reference data (administrative divisions, lookup codes) -- no personal data

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

LOCK TABLES `age` WRITE;
/*!40000 ALTER TABLE `age` DISABLE KEYS */;
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID01','(၃) နှစ်အထက်');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID02','(၁) နှစ် မှ (၃) နှစ်');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID03','(၁) နှစ်အောက်');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID04','(၆) လ အထက်');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID05','(၂) လ မှ (၆) လ');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID06','(၂) လ အောက်');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID07','ရက်သားမှ (၆) ပတ်သား');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID08','(၇) ပတ်သားမှ (၁၈) ပတ်သား');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID09','(၁၉) ပတ်သားနှင့်အထက်');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID10','ရက်သားမှ (၂၀) ပတ်သား');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID11','(၂၁) ပတ်သားနှင့်အထက်');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID12','ရက်သားမှ (၈) ပတ်သား');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID13','(၉) ပတ်သားမှ (၁၆) ပတ်သား');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID14','(၁၇) ပတ်သားနှင့်အထက်');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID15','(၇) ပတ်သားမှ (၂၄) ပတ်သား');
INSERT INTO `age` (`ageID`, `ageName`) VALUES ('ageID16','(၂၅) ပတ်သားနှင့်အထက်');
/*!40000 ALTER TABLE `age` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `agetype` WRITE;
/*!40000 ALTER TABLE `agetype` DISABLE KEYS */;
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID01','(၃) နှစ်အထက်','atID01','');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID02','(၁) နှစ် မှ (၃) နှစ်','atID01',NULL);
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID03','(၁) နှစ်အောက်','atID01',NULL);
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID04','(၆) လ အထက်','atID02',NULL);
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID05','(၂) လ မှ (၆) လ','atID02',NULL);
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID06','(၂) လ အောက်','atID02',NULL);
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID07','ငယ် (ရက်သားမှ (၆) ပတ်သား)','atID03','lsID01');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID08','လတ်((၇) ပတ်သားမှ (၁၈) ပတ်သား)','atID03','lsID01');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID09','ကြီး((၁၉) ပတ်သားနှင့်အထက်)','atID03','lsID01');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID10','ငယ်_လတ်(ရက်သားမှ (၂၀) ပတ်သား)','atID03','lsID03');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID11','ကြီး(၂၁) ပတ်သားနှင့်အထက်','atID03','lsID03');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID12','ငယ်(ရက်သားမှ (၈) ပတ်သား)','atID03','lsID04');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID13','လတ်((၉) ပတ်သားမှ (၁၆) ပတ်သား)','atID03','lsID04');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID14','(ကြီး) (၁၇) ပတ်သားနှင့်အထက်','atID03','lsID04');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID15','ငယ် (ရက်သားမှ (၆) ပတ်သား)','atID03','lsID07');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID16','လတ်((၇) ပတ်သားမှ (၂၄) ပတ်သား)','atID03','lsID07');
INSERT INTO `agetype` (`ageID`, `ageName`, `animalTypeID`, `animalID`) VALUES ('ageID17','ကြီး((၂၅) ပတ်သားနှင့်အထက်)','lsID07','atID03');
/*!40000 ALTER TABLE `agetype` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `animaltype` WRITE;
/*!40000 ALTER TABLE `animaltype` DISABLE KEYS */;
INSERT INTO `animaltype` (`animalTypeID`, `animalName`) VALUES ('atID01','တိရစ္ဆာန်ကြီး');
INSERT INTO `animaltype` (`animalTypeID`, `animalName`) VALUES ('atID02','တိရစ္ဆာန်ငယ်');
INSERT INTO `animaltype` (`animalTypeID`, `animalName`) VALUES ('atID03','ကြက်/ဘဲ/ငုံး');
INSERT INTO `animaltype` (`animalTypeID`, `animalName`) VALUES ('atID04','မျိုးတိရစ္ဆာန်');
/*!40000 ALTER TABLE `animaltype` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `breedingstock` WRITE;
/*!40000 ALTER TABLE `breedingstock` DISABLE KEYS */;
INSERT INTO `breedingstock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('bsID01','ဒေသနွား','atID04');
INSERT INTO `breedingstock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('bsID02','ဒေသကျွဲ','atID04');
INSERT INTO `breedingstock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('bsID03','နို့စားကျွဲ','atID04');
INSERT INTO `breedingstock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('bsID04','ဝက်','atID04');
INSERT INTO `breedingstock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('bsID05','ဆိတ်','atID04');
INSERT INTO `breedingstock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('bsID06','သိုး','atID04');
/*!40000 ALTER TABLE `breedingstock` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `district` WRITE;
/*!40000 ALTER TABLE `district` DISABLE KEYS */;
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s01','d01','ချီဖွေခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s01','d02','တနိုင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s01','d03','ပူတာအိုခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s01','d04','ဗန်းမော်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s01','d05','မိုးညှင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s01','d06','မြစ်ကြီးနားခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s02','d01','ဒီးမော့ဆိုခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s02','d02','ဘောလခဲခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s02','d03','မယ်စဲ့ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s02','d04','လွိုင်ကော်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s03','d01','ကော့ကရိတ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s03','d02','ကြာအင်းဆိပ်ကြီးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s03','d03','ဖာပွန်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s03','d04','ဘားအံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s03','d05','မြဝတီခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s03','d06','သံတောင်ကြီးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s04','d01','တီးတိန်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s04','d02','ပလက်ဝခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s04','d03','ဖလမ်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s04','d04','မတူပီခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s04','d05','မင်းတပ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s04','d06','ဟားခါးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d01','နာဂကိုယ်ပိုင်အုပ်ချုပ်ခွင့်ရဒေသ');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d02','ကလေးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d03','ကသာခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d04','ကောလင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d05','ကန့်ဘလူခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d06','ခန္တီးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d07','စစ်ကိုင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d08','တမူးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d09','မော်လိုက်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d10','မုံရွာခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d11','ယင်းမာပင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d12','ရေဦးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d13','ရွှေဘိုခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s05','d14','ဟုမ္မလင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s06','d01','ကော့သောင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s06','d02','ထားဝယ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s06','d03','ဘုတ်ပြင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s06','d04','မြိတ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s07','d01','ညောင်လေးပင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s07','d02','တောင်ငူခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s07','d03','နတ်တလင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s07','d04','ပဲခူးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s07','d05','ပြည်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s07','d06','သာယာဝတီခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s08','d01','ချောက်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s08','d02','ဂန့်ဂေါခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s08','d03','ပခုက္ကူခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s08','d04','မကွေးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s08','d05','မင်းဘူးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s08','d06','သရက်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s08','d07','အောင်လံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d01','ကျောက်ဆည်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d02','‌ညောင်ဦးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d03','တံတားဦးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d04','ပြင်ဦးလွင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d05','မဟာအောင်မြေခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d06','မိတ္ထီလာခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d07','မြင်းခြံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d08','ရမည်းသင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d09','သပိတ်ကျင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d10','အမရပူရခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s09','d11','အောင်မြေသာစံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s10','d01','ကျိုက်ထိုခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s10','d02','မော်လမြိုင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s10','d03','ရေးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s10','d04','သထုံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s11','d01','ကျောက်ဖြူခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s11','d02','စစ်တွေခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s11','d03','တောင်ကုတ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s11','d04','မောင်တောခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s11','d05','မြောက်ဦးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s11','d06','သံတွဲခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s11','d07','အမ်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d01','ကမာရွတ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d02','ကျောက်တံတားခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d03','တိုက်ကြီးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d04','တွံတေးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d05','ဒဂုံမြို့သစ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d06','ဗိုလ်တထောင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d07','မရမ်းကုန်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d08','မင်္ဂလာဒုံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d09','မှော်ဘီခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d10','လှည်းကူးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d11','သင်္ဃန်းကျွန်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d12','သန်လျင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d13','အလုံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s12','d14','အင်းစိန်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d01','မက်မန်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d02','ဟိုပန်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d03','ဓနုကိုယ်ပိုင်အုပ်ချုပ်ခွင့်ရဒေသ');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d04','ပအိုဝ်းကိုယ်ပိုင်အုပ်ချုပ်ခွင့်ရဒေသ');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d05','ပလောင်ကိုယ်ပိုင်အုပ်ချုပ်ခွင့်ရဒေသ');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d06','ကိုးကန့်ကိုယ်ပိုင်အုပ်ချုပ်ခွင့်ရဒေသ');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d07','ကလောခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d08','ကျောက်မဲခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d09','ကျိုင်းတုံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d10','ကွတ်ခိုင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d11','တာချီလိတ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d12','တောင်ကြီးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d13','တန့်ယန်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d14','နမ့်စန်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d15','မူဆယ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d16','မိုးမိတ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d17','မိုင်းဆတ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d18','မိုင်းတုံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d19','မိုင်းယောင်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d20','မိုင်းယန်းခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d21','မိုင်းရှူးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d22','မိုင်းလားခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d23','လားရှိုးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d24','လင်းခေးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s13','d25','လွိုင်လင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s14','d01','ကျုံပျော်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s14','d02','ပုသိမ်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s14','d03','ဖျာပုံခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s14','d04','မအူပင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s14','d05','မြောင်းမြခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s14','d06','မြန်အောင်ခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s14','d07','လပွတ္တာခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s14','d08','ဟင်္သာတခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s15','d01','ဇေယျာသီရိခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s15','d02','ပျဉ်းမနားခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s15','d03','လယ်ဝေးခရိုင်');
INSERT INTO `district` (`stateID`, `districtID`, `districtName`) VALUES ('s15','d04','ဥတ္တရခရိုင်');
/*!40000 ALTER TABLE `district` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `gender` WRITE;
/*!40000 ALTER TABLE `gender` DISABLE KEYS */;
INSERT INTO `gender` (`genderID`, `genderName`) VALUES ('g01','အထီး');
INSERT INTO `gender` (`genderID`, `genderName`) VALUES ('g02','သင်းကွပ်အထီး');
INSERT INTO `gender` (`genderID`, `genderName`) VALUES ('g03','အမ');
/*!40000 ALTER TABLE `gender` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `largeanimals` WRITE;
/*!40000 ALTER TABLE `largeanimals` DISABLE KEYS */;
INSERT INTO `largeanimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('laID01','ဒေသနွား','atID01');
INSERT INTO `largeanimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('laID02','အသားစားနွား','atID01');
INSERT INTO `largeanimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('laID03','နို့စားနွား','atID01');
INSERT INTO `largeanimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('laID04','နွားနောက်','atID01');
INSERT INTO `largeanimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('laID05','ဒေသကျွဲ','atID01');
INSERT INTO `largeanimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('laID06','ခိုင်းကျွဲ','atID01');
INSERT INTO `largeanimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('laID07','နို့စားကျွဲ','atID01');
INSERT INTO `largeanimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('laID08','မြင်း','atID01');
INSERT INTO `largeanimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('laID09','ဆင်','atID01');
/*!40000 ALTER TABLE `largeanimals` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `largespecies` WRITE;
/*!40000 ALTER TABLE `largespecies` DISABLE KEYS */;
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0101','ပြာစိမ်း','laID01');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0102','ရွှေနီ','laID01');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0103','စာဥ','laID01');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0104','စံပယ်','laID01');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0105','ရှမ်းနွားပု','laID01');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0201','ဘရာမန်(အသားစားမျိုး)','laID02');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0202','အန်ဂတ်စ်(အသားစားမျိုးစပ်)','laID02');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0301','ဖရီရှန် ','laID03');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0302','ဂျာစီ','laID03');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0303','ဘရောင်းဆွစ်','laID03');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0401','နွားနောက်','laID04');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0501','နမူရီ(ရွှံလူးကျွဲ)','laID05');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0502','ဂျီရန်ဂီ(ရွှံလူးကျွဲ)','laID05');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0503','တိုင်းရင်းကျွဲ(ရွှံလူးကျွဲ)','laID05');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0601','ခိုင်းကျွဲ','laID06');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0701','မူယား(ရေစိမ်ကျွဲ)','laID07');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0702','ဆာတီ(ရေစိမ်ကျွဲ)','laID07');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0703','နီလီရာဘီ(ရေစိမ်ကျွဲ)','laID07');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0704','ဂျဖာရာဘဒီ(ရေစိမ်ကျွဲ)','laID07');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0801','မြင်း','laID08');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0802','မြည်း','laID08');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0803','လား','laID08');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0804','မြင်းပု','laID08');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0805','အာဖရိကဆင်','laID09');
INSERT INTO `largespecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('laSID0806','ဆာဗားနား','laID09');
/*!40000 ALTER TABLE `largespecies` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `livestock` WRITE;
/*!40000 ALTER TABLE `livestock` DISABLE KEYS */;
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID01','ဥစားကြက်','atID03');
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID02','အသားစားကြက်','atID03');
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID03','ဒေသကြက်','atID03');
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID04','ဥစားဘဲ','atID03');
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID05','အသားစားဘဲ','atID03');
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID06','ဒေသဘဲ/ဓာတ်ဘဲ','atID03');
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID07','ကြက်ဆင်','atID03');
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID08','ဘဲငန်း','atID03');
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID09','မန်ဒါလီ','atID03');
INSERT INTO `livestock` (`animalID`, `animalName`, `animalTypeID`) VALUES ('lsID10','ငုံး','atID03');
/*!40000 ALTER TABLE `livestock` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `livestockspecies` WRITE;
/*!40000 ALTER TABLE `livestockspecies` DISABLE KEYS */;
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0101','lsa Brown','lsID01');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0102','Boven Goldline','lsID01');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0103','Hyline Brown','lsID01');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0201','ROSS(Hi-chick)','lsID02');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0202','COBB(Hi-chick)','lsID02');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0301','စစ်တကောင်း','lsID03');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0302','တိန်ညင်','lsID03');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0303','အင်ပင်ဝ','lsID03');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0304','ကြက်မဲ','lsID03');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0305','တိုက်ကြက်','lsID03');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0306','လည်ပြောင်','lsID03');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0307','တောင်ပျံ','lsID03');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0401','ကာကီကင်းဘဲ(ဥစားဘဲ)','lsID04');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0501','ချယ်ရီဘယ်ရီ(အသားစားဘဲ)','lsID05');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0601','ဒေသဘဲ/ဓာတ်ဘဲ','lsID06');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0701','ကြက်ဆင်','lsID07');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0801','ဘဲငန်း','lsID08');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID0901','ဘဲငန်း','lsID09');
INSERT INTO `livestockspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('lsSID1001','မန်ဒါလီ','lsID10');
/*!40000 ALTER TABLE `livestockspecies` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `state` WRITE;
/*!40000 ALTER TABLE `state` DISABLE KEYS */;
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s01','ကချင်ပြည်နယ်');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s02','ကယားပြည်နယ်');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s03','ကရင်ပြည်နယ်');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s04','ချင်းပြည်နယ်');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s05','စစ်ကိုင်းတိုင်းဒေသကြီး');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s06','တနင်္သာရီတိုင်းဒေသကြီး');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s07','ပဲခူးတိုင်းဒေသကြီး');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s08','မကွေးတိုင်းဒေသကြီး');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s09','မန္တလေးတိုင်းဒေသကြီး');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s10','မွန်ပြည်နယ်');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s11','ရခိုင်ပြည်နယ်');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s12','ရန်ကုန်တိုင်းဒေသကြီး');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s13','ရှမ်းပြည်နယ်');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s14','ဧရာဝတီတိုင်းဒေသကြီး');
INSERT INTO `state` (`stateID`, `stateName`) VALUES ('s15','ပြည်ထောင်စုနယ်မြေ');
/*!40000 ALTER TABLE `state` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `township` WRITE;
/*!40000 ALTER TABLE `township` DISABLE KEYS */;
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d01','t01','ချီဖွေမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d01','t02','ဆော့လော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d02','t01','တနိုင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d03','t01','ခေါင်လန်ဖူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d03','t02','ဆွမ်ပရာဘွမ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d03','t03','နောင်မွန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d03','t04','ပူတာအိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d03','t05','မချမ်းဘောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d04','t01','ဗန်းမော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d04','t02','မံစီမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d04','t03','မိုးမောက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d04','t04','ရွှေကူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d05','t01','ဖားကန့်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d05','t02','မိုးကောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d05','t03','မိုးညှင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d06','t01','မြစ်ကြီးနားမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d06','t02','ဝိုင်းမော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s01','d06','t03','အင်ဂျန်းယန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s02','d01','t01','ဒီးမော့ဆိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s02','d01','t02','ဖရူဆိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s02','d02','t01','ဖားဆောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s02','d02','t02','ဘောလခဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s02','d03','t01','မယ်စဲ့မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s02','d04','t01','ရှားတောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s02','d04','t02','လွိုင်ကော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s03','d01','t01','ကော့ကရိတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s03','d02','t01','ကြာအင်းဆိပ်ကြီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s03','d03','t01','ဖာပွန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s03','d04','t01','ဘားအံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s03','d04','t02','လှိုင်းဘွဲ့မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s03','d05','t01','မြဝတီမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s03','d06','t01','သံတောင်ကြီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s04','d01','t01','တီးတိန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s04','d01','t02','တွန်းဇံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s04','d02','t01','ပလက်ဝမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s04','d03','t01','ဖလမ်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s04','d04','t01','မတူပီမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s04','d05','t01','ကန်ပက်လက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s04','d05','t02','မင်းတပ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s04','d06','t01','ထန်တလန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s04','d06','t02','ဟားခါးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d01','t01','နန်းယွန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d01','t02','လဟယ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d01','t03','လေရှီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d02','t01','ကလေးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d02','t02','ကလေးဝမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d02','t03','မင်းကင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d03','t01','ကသာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d03','t02','ထီးချိုင့်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d03','t03','ဗန်းမောက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d03','t04','အင်းတော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d04','t01','ကောလင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d04','t02','ပင်လည်ဘူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d04','t03','ဝန်းသိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d05','t01','ကန့်ဘလူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d05','t02','ကျွန်းလှမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d06','t01','ခန္တီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d07','t01','စစ်ကိုင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d07','t02','မြင်းမူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d07','t03','မြောင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d08','t01','တမူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d09','t01','ဖောင်းပြင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d09','t02','မော်လိုက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d10','t01','ချောင်းဦးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d10','t02','ဘုတလင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d10','t03','မုံရွာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d10','t04','အရာတော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d11','t01','ကနီမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d11','t02','ဆားလင်းကြီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d11','t03','ပုလဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d11','t04','ယင်းမာပင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d12','t01','ဒီပဲယင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d12','t02','တန့်ဆည်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d12','t03','ရေဦးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d13','t01','ခင်ဦးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d13','t02','ရွှေဘိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d13','t03','ဝက်လက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s05','d14','t01','ဟုမ္မလင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d01','t01','ကော့သောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d02','t01','ထားဝယ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d02','t02','ရေဖြူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d02','t03','လောင်းလုံးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d02','t04','သရက်ချောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d03','t01','ဘုတ်ပြင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d04','t01','ကျွန်းစုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d04','t02','တနင်္သာရီမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d04','t03','ပုလောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s06','d04','t04','မြိတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d01','t01','ကျောက်ကြီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d01','t02','ကျောက်တံခါးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d01','t03','ညောင်လေးပင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d01','t04','ဒိုက်ဦးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d01','t05','ရွှေကျင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d02','t01','တောင်ငူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d02','t02','ထန်းတပင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d02','t03','ဖြူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d02','t04','ရေတာရှည်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d02','t05','အုတ်တွင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d03','t01','ဇီးကုန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d03','t02','နတ်တလင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d03','t03','ပေါင်းတည်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d03','t04','သဲကုန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d04','t01','ကဝမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d04','t02','ပဲခူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d04','t03','ဝေါမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d04','t04','သနပ်ပင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d05','t01','ပေါက်ခေါင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d05','t02','ပန်းတောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d05','t03','ပြည်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d05','t04','ရွှေတောင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d06','t01','ကြို့ပင်ကောက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d06','t02','မိုးညိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d06','t03','မင်းလှမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d06','t04','လက်ပံတန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d06','t05','သာယာဝတီမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s07','d06','t06','အုတ်ဖိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d01','t01','ချောက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d01','t02','ရေနံချောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d02','t01','ဂန့်ဂေါမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d02','t02','ဆောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d02','t03','ထီးလင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d03','t01','ဆိပ်ဖြူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d03','t02','ပခုက္ကူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d03','t03','ပေါက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d03','t04','မြိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d03','t05','ရေစကြိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d04','t01','တောင်တွင်းကြီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d04','t02','နတ်မောက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d04','t03','မကွေးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d04','t04','မြို့သစ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d05','t01','ငဖဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d05','t02','စလင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d05','t03','စေတုတ္ထရာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d05','t04','ပွင့်ဖြူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d05','t05','မင်းဘူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d06','t01','ကံမမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d06','t02','မင်းတုန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d06','t03','မင်းလှမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d06','t04','သရက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d07','t01','ဆင်ပေါင်ဝဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s08','d07','t02','အောင်လံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d01','t01','ကျောက်ဆည်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d01','t02','စဥ့်ကိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d01','t03','မြစ်သားမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d02','t01','ကျောက်ပန်းတောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d02','t02','ညောင်ဦးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d03','t01','ငါန်းဇွန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d03','t02','တံတားဦးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d04','t01','ပြင်ဦးလွင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d05','t01','ချမ်းမြသာစည်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d05','t02','ချမ်းအေးသာစံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d05','t03','ပြည်ကြီးတံခွန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d05','t04','မဟာအောင်မြေမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d06','t01','မလှိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d06','t02','မိတ္ထီလာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d06','t03','ဝမ်းတွင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d06','t04','သာစည်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d07','t01','တောင်သာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d07','t02','နွားထိုးကြီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d07','t03','မြင်းခြံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d08','t01','ပျော်ဘွယ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d08','t02','ရမည်းသင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d09','t01','စဥ့်ကူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d09','t02','မိုးကုတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d09','t03','သပိတ်ကျင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d10','t01','အမရပူရမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d11','t01','ပုသိမ်ကြီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d11','t02','မတ္တရာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s09','d11','t03','အောင်မြေသာစံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d01','t01','ကျိုက်ထိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d01','t02','ဘီးလင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d02','t01','ကျိုက်မ‌ရောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d02','t02','ချောင်းဆုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d02','t03','မုဒုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d02','t04','မော်လမြိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d02','t05','သံဖြူဇရပ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d03','t01','ရေးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d04','t01','ပေါင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s10','d04','t02','သထုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d01','t01','ကျောက်ဖြူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d01','t02','ရမ်းဗြဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d02','t01','စစ်တွေမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d02','t02','ပေါက်တောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d02','t03','ပုဏ္ဏားကျွန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d02','t04','ရသေ့တောင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d03','t01','တောင်ကုတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d03','t02','မာန်အောင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d04','t01','ဘူးသီးတောင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d04','t02','မောင်တောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d05','t01','ကျောက်တော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d05','t02','မင်းပြားမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d05','t03','မြေပုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d05','t04','မြောက်ဦးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d06','t01','ဂွမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d06','t02','သံတွဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s11','d07','t01','အမ်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d01','t01','ကမာရွတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d01','t02','ဗဟန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d02','t01','ကျောက်တံတားမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d02','t02','ဒဂုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d02','t03','ပန်းဘဲတန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d02','t04','လသာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d02','t05','လမ်းမတော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d03','t01','တိုက်ကြီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d04','t01','ကော့မှူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d04','t02','ကွမ်းခြံကုန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d04','t03','ဆိပ်ကြီး/ခနောင်တိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d04','t04','တွံတေးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d04','t05','ဒလမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d05','t01','ဒဂုံမြို့သစ်(ဆိပ်ကမ်း)မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d05','t02','ဒဂုံမြို့သစ်(တောင်ပိုင်း)မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d05','t03','ဒဂုံမြို့သစ်(မြောက်ပိုင်း)မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d05','t04','ဒဂုံမြို့သစ်(အရှေ့ပိုင်း)မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d06','t01','ဒေါပုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d06','t02','ပုဇွန်တောင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d06','t03','ဗိုလ်တထောင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d06','t04','မင်္ဂလာတောင်ညွန့်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d06','t05','သာကေတမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d07','t01','မရမ်းကုန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d07','t02','မြောက်ဥက္ကလာပမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d07','t03','လှိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d08','t01','မင်္ဂလာဒုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d08','t02','ရွှေပြည်သာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d09','t01','ထန်းတပင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d09','t02','မှော်ဘီမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d10','t01','လှည်းကူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d11','t01','တာမွေမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d11','t02','တောင်ဥက္ကလာပမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d11','t03','ရန်ကင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d11','t04','သင်္ဃန်းကျွန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d12','t01','ကိုကိုးကျွန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d12','t02','ကျောက်တန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d12','t03','ခရမ်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d12','t04','သန်လျင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d12','t05','သုံးခွမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d13','t01','ကြည့်မြင်တိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d13','t02','စမ်းချောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d13','t03','အလုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d14','t01','လှိုင်သာယာ(အနောက်ပိုင်း)မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d14','t02','လှိုင်သာယာ(အရှေ့ပိုင်း)မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s12','d14','t03','အင်းစိန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d01','t01','နားဖန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d01','t02','ပန်ဆန်း(ပန်ခမ်း)မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d01','t03','မက်မန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d02','t01','ပန်ဝိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d02','t02','မိုင်းမောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d02','t03','ဟိုပန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d03','t01','ပင်းတယမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d03','t02','ရွာငံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d04','t01','ဆီဆိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d04','t02','ပင်လောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d04','t03','ဟိုပုံးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d05','t01','နမ့်ဆန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d05','t02','မန်တုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d06','t01','ကုန်းကြမ်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d06','t02','လောက်ကိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d07','t01','ကလောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d07','t02','ညောင်ရွှေမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d07','t03','ဖယ်ခုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d08','t01','ကျောက်မဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d08','t02','နမ္မတူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d08','t03','နောင်ချိုမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d08','t04','သီပေါမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d09','t01','ကျိုင်းတုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d09','t02','မိုင်းခတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d09','t03','မိုင်းပျဉ်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d10','t01','ကွတ်ခိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d11','t01','တာချီလိတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d11','t02','မိုင်းဖြတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d12','t01','တောင်ကြီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d12','t02','ရပ်‌စောက်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d13','t01','တန့်ယန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d13','t02','မိုင်းရယ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d14','t01','ကွန်ဟိန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d14','t02','နမ့်စန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d14','t03','မိုးနဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d15','t01','နမ့်ခမ်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d15','t02','မူဆယ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d16','t01','မဘိမ်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d16','t02','မိုးမိတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d17','t01','မိုင်းဆတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d18','t01','မိုင်းတုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d19','t01','မိုင်းယောင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d20','t01','မိုင်းယန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d21','t01','ကျေးသီးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d21','t02','မိုင်းရှူးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d22','t01','မိုင်းလားမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d23','t01','ကွမ်းလုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d23','t02','လားရှိုးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d23','t03','သိန္နီမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d24','t01','မိုင်းပန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d24','t02','မောက်မယ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d24','t03','လင်းခေးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d25','t01','မိုင်းကိုင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d25','t02','လဲချားမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s13','d25','t03','လွိုင်လင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d01','t01','ကျောင်းကုန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d01','t02','ကျုံပျော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d01','t03','ရေကြည်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d02','t01','ကန်ကြီးထောင့်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d02','t02','ငပုတောမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d02','t03','ပုသိမ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d02','t04','သာပေါင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d03','t01','ကျိုက်လတ်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d03','t02','ဒေးဒရဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d03','t03','ဖျာပုံမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d03','t04','ဘိုကလေးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d04','t01','ညောင်တုန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d04','t02','ဓနုဖြူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d04','t03','ပန်းတနော်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d04','t04','မအူပင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d05','t01','မြောင်းမြမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d05','t02','ဝါးခယ်မမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d05','t03','အိမ်မဲမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d06','t01','ကြံခင်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d06','t02','မြန်အောင်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d06','t03','အင်္ဂပူမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d07','t01','မော်လမြိုင်ကျွန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d07','t02','လပွတ္တာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d08','t01','ဇလွန်မြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d08','t02','လေးမျက်နှာမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s14','d08','t03','ဟင်္သာတမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s15','d01','t01','ဇေယျာသီရိမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s15','d01','t02','ပုဗ္ဗသီရိမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s15','d02','t01','ဇမ္ဗူသီရိမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s15','d02','t02','ပျဉ်းမနားမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s15','d03','t01','ဒက္ခိဏသီရိမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s15','d03','t02','လယ်ဝေးမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s15','d04','t01','တပ်ကုန်းမြို့နယ်');
INSERT INTO `township` (`stateID`, `districtID`, `townshipID`, `townshipName`) VALUES ('s15','d04','t02','ဥတ္တရသီရိမြို့နယ်');
/*!40000 ALTER TABLE `township` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `userrole` WRITE;
/*!40000 ALTER TABLE `userrole` DISABLE KEYS */;
INSERT INTO `userrole` (`roleId`, `roleName`) VALUES (1,'admin');
INSERT INTO `userrole` (`roleId`, `roleName`) VALUES (2,'union');
INSERT INTO `userrole` (`roleId`, `roleName`) VALUES (3,'state');
INSERT INTO `userrole` (`roleId`, `roleName`) VALUES (4,'distinct');
INSERT INTO `userrole` (`roleId`, `roleName`) VALUES (5,'township');
INSERT INTO `userrole` (`roleId`, `roleName`) VALUES (6,'enumerator');
/*!40000 ALTER TABLE `userrole` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `younganimals` WRITE;
/*!40000 ALTER TABLE `younganimals` DISABLE KEYS */;
INSERT INTO `younganimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('yaID01','ဆိတ်','atID02');
INSERT INTO `younganimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('yaID02','သိုး','atID02');
INSERT INTO `younganimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('yaID03','ဝက်','atID02');
INSERT INTO `younganimals` (`animalID`, `animalName`, `animalTypeID`) VALUES ('yaID04','ခွေး','atID02');
/*!40000 ALTER TABLE `younganimals` ENABLE KEYS */;
UNLOCK TABLES;

LOCK TABLES `youngspecies` WRITE;
/*!40000 ALTER TABLE `youngspecies` DISABLE KEYS */;
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0101','ထိန်စမ်း (ဒေသဆိတ်)','yaID01');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0102','ဂျိတ်နီ (ဒေသဆိတ်)','yaID01');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0103','ဝေသာလီ (ဒေသဆိတ်)','yaID01');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0104','ဘိုဝါ (အသားတိုးဆိတ်)','yaID01');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0105','Nubian (အသားတိုးဆိတ်)','yaID01');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0106','Sirohi (အသားတိုးဆိတ်)','yaID01');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0107','ဆာနန်(နို့စားဆိတ်)','yaID01');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0201','ကုလားသိုး','yaID02');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0301','ဒေသဝက်','yaID03');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0302','DYL','yaID03');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0303','Landrace','yaID03');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0304','Yorkshire','yaID03');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0305','Duroc','yaID03');
INSERT INTO `youngspecies` (`speciesID`, `speciesName`, `animalID`) VALUES ('yaSID0401','ခွေး','yaID04');
/*!40000 ALTER TABLE `youngspecies` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;


-- Synthetic enumerator records for the demo build (no real names or phones)
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d03','QVDEMO01','QV Demo 01','s04','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d01','QVDEMO02','QV Demo 02','s03','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d02','QVDEMO03','QV Demo 03','s05','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d04','QVDEMO04','QV Demo 04','s02','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d03','QVDEMO05','QV Demo 05','s02','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d06','QVDEMO06','QV Demo 06','s04','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d02','QVDEMO07','QV Demo 07','s02','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d05','QVDEMO08','QV Demo 08','s04','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d01','QVDEMO09','QV Demo 09','s02','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d02','QVDEMO10','QV Demo 10','s04','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d04','QVDEMO11','QV Demo 11','s04','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d06','QVDEMO12','QV Demo 12','s01','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d01','QVDEMO13','QV Demo 13','s04','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d05','QVDEMO14','QV Demo 14','s01','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d04','QVDEMO15','QV Demo 15','s03','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d05','QVDEMO16','QV Demo 16','s03','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d01','QVDEMO17','QV Demo 17','s05','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d04','QVDEMO18','QV Demo 18','s01','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d02','QVDEMO19','QV Demo 19','s03','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d03','QVDEMO20','QV Demo 20','s03','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d06','QVDEMO21','QV Demo 21','s03','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d03','QVDEMO22','QV Demo 22','s05','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d03','QVDEMO23','QV Demo 23','s01','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d02','QVDEMO24','QV Demo 24','s01','t01');
INSERT IGNORE INTO `qv` (`districtID`,`QVID`,`QVName`,`stateID`,`townshipID`) VALUES ('d01','QVDEMO25','QV Demo 25','s01','t01');

-- Bootstrap admin account: loginName 'admin', password 'LBVDdemo#2026'
INSERT IGNORE INTO `user` (`userID`,`userName`,`userRole`,`loginName`,`password`,`stateID`,`status`) VALUES (1,'LBVD Demo Admin',1,'admin','pbkdf2_sha256$310000$T6td6cYFSyx5rXr7s2TlPQ==$qMXItPUI6Z2HfY5Z0fbfBhVms_jRtChLO9fbNXLXN_s=','s07',1);
-- Real superadmin profile (role 1), no contact details. userID 100 avoids the synthetic demo admin at ID 1.
INSERT IGNORE INTO `user` (`userID`,`userName`,`userRole`,`loginName`,`password`,`stateID`,`districtID`,`townshipID`,`QVID`,`status`) VALUES (100,'BagoAdmin',1,'BagoAdmin','pbkdf2_sha256$310000$kM6cUq6YgFKubh-1s2rN7g==$4SuFP1VXHSZOVU2fnVmPW6YR0IiG8iou9PKvP2uLXXc=','s07','d04','t02','',1);
-- Demo enumerator account matching the real "mgmg" profile, but without any real contact details.
INSERT IGNORE INTO `user` (`userID`,`userName`,`userRole`,`loginName`,`password`,`stateID`,`districtID`,`townshipID`,`QVID`,`status`) VALUES (7,'Mg Mg',6,'mgmg','pbkdf2_sha256$310000$2ICgK_CmfT9v_Nvn2xwplw==$CDcg_f0a12McJZnUx7WWQ6_dugbQkgMulRLtTOMkUtE=','s07','d02','t01','W05',1);
