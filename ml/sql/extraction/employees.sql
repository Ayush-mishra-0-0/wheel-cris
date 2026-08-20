-- Bronze/raw Employees lookup extract: decodes LwrTakenBy into the full measurer's
-- name. Also carries EmpSection (-> Sections.SecId) and EmpFunctionalLocation
-- (-> FunctionalLocations.FLocId) so the website's "Section" column can be rebuilt.
SELECT
    EmpId,
    EmpCode,
    EmpFullName,
    EmpFirstName,
    EmpLastName,
    EmpMiddleName,
    EmpSection,
    EmpFunctionalLocation,
    EmpDesignation,
    EmpStatus
FROM Employees
ORDER BY EmpId;