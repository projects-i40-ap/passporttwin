import os
import requests
import logging

logger = logging.getLogger("passporttwin.aas")
BASYX_AAS_URL = os.getenv("BASYX_AAS_URL", "http://basyx-aas:4001/aasServer")

class AASBuilder:
    @staticmethod
    def sync_shell_and_nameplate(instrument, instrument_type) -> bool:
        """Proyecta un activo canónico hacia Eclipse BaSyx AAS Server v1.4.0."""
        clean_serial = instrument.serial_number.replace("-", "_")
        aas_id = f"AAS_{clean_serial}"
        asset_id = f"Asset_{clean_serial}"
        sm_id = f"Submodel_Nameplate_{clean_serial}"

        # 1. Payload de la AAS (identification.id DEBE coincidir con el ID de la URL)
        shell_payload = {
            "idShort": aas_id,
            "identification": {
                "id": aas_id,
                "idType": "Custom"
            },
            "asset": {
                "idShort": asset_id,
                "identification": {
                    "id": asset_id,
                    "idType": "Custom"
                },
                "kind": "Instance"
            },
            "submodels": []
        }

        # 2. Payload del Submodelo Digital Nameplate (IDTA 02006)
        nameplate_payload = {
            "idShort": "Nameplate",
            "identification": {
                "id": sm_id,
                "idType": "Custom"
            },
            "semanticId": {
                "keys": [
                    {
                        "type": "GlobalReference",
                        "local": False,
                        "value": "https://admin-shell.io/zvei/nameplate/1/0/Nameplate",
                        "idType": "IRI"
                    }
                ]
            },
            "submodelElements": [
                {
                    "idShort": "ManufacturerName",
                    "modelType": {"name": "Property"},
                    "valueType": "string",
                    "value": str(instrument.manufacturer)
                },
                {
                    "idShort": "ManufacturerProductDesignation",
                    "modelType": {"name": "Property"},
                    "valueType": "string",
                    "value": str(instrument.model)
                },
                {
                    "idShort": "SerialNumber",
                    "modelType": {"name": "Property"},
                    "valueType": "string",
                    "value": str(instrument.serial_number)
                },
                {
                    "idShort": "PhysicalQuantity",
                    "modelType": {"name": "Property"},
                    "valueType": "string",
                    "value": str(instrument_type.magnitude)
                }
            ]
        }

        headers = {"Content-Type": "application/json"}

        try:
            # A. Registrar o actualizar la AAS en el Aggregator de BaSyx
            url_shell = f"{BASYX_AAS_URL}/shells/{aas_id}"
            resp_shell = requests.put(url_shell, json=shell_payload, headers=headers, timeout=5)
            if resp_shell.status_code not in [200, 201]:
                logger.error(f"Error creando AAS ({resp_shell.status_code}): {resp_shell.text}")
                return False

            # B. Registrar el Submodelo dentro de la AAS
            url_submodel = f"{BASYX_AAS_URL}/shells/{aas_id}/aas/submodels/Nameplate"
            resp_sm = requests.put(url_submodel, json=nameplate_payload, headers=headers, timeout=5)
            if resp_sm.status_code not in [200, 201]:
                logger.error(f"Error vinculando submodelo ({resp_sm.status_code}): {resp_sm.text}")
                return False

            return True

        except Exception as e:
            logger.error(f"Fallo de comunicación con BaSyx AAS: {str(e)}")
            return False
    @staticmethod
    def sync_calibration_submodel(instrument, calibration_event) -> bool:
        """Proyecta el historial de calibración aceptado al servidor BaSyx."""
        clean_serial = instrument.serial_number.replace("-", "_")
        aas_id = f"AAS_{clean_serial}"
        sm_id = f"Submodel_Calibration_{clean_serial}"

        payload = {
            "idShort": "CalibrationHistory",
            "identification": {
                "id": sm_id,
                "idType": "Custom"
            },
            "semanticId": {
                "keys": [
                    {
                        "type": "GlobalReference",
                        "local": False,
                        "value": "urn:passporttwin:submodel:calibration:1:0",
                        "idType": "IRI"
                    }
                ]
            },
            "submodelElements": [
                {
                    "idShort": "LastCalibrationDate",
                    "modelType": {"name": "Property"},
                    "valueType": "string",
                    "value": str(calibration_event.calibration_date)
                },
                {
                    "idShort": "NextDueDate",
                    "modelType": {"name": "Property"},
                    "valueType": "string",
                    "value": str(calibration_event.next_due_date)
                },
                {
                    "idShort": "ErrorValue",
                    "modelType": {"name": "Property"},
                    "valueType": "double",
                    "value": str(calibration_event.error_value)
                },
                {
                    "idShort": "Tolerance",
                    "modelType": {"name": "Property"},
                    "valueType": "double",
                    "value": str(calibration_event.tolerance)
                },
                {
                    "idShort": "CalibrationResult",
                    "modelType": {"name": "Property"},
                    "valueType": "string",
                    "value": str(calibration_event.result)
                }
            ]
        }

        headers = {"Content-Type": "application/json"}
        try:
            url = f"{BASYX_AAS_URL}/shells/{aas_id}/aas/submodels/CalibrationHistory"
            resp = requests.put(url, json=payload, headers=headers, timeout=4)
            return resp.status_code in [200, 201]
        except Exception as e:
            logger.error(f"Error sincronizando Submodelo Calibration en BaSyx: {str(e)}")
            return False