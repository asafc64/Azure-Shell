import jsonpickle

from cloudshell.cp.azure.models.azure_cloud_provider_resource_model import AzureCloudProviderResourceModel
from cloudshell.cp.azure.models.deploy_azure_vm_resource_models import DeployAzureVMResourceModel
from cloudshell.cp.azure.models.deploy_azure_vm_resource_models import DeployAzureVMFromCustomImageResourceModel
from cloudshell.cp.azure.common.deploy_data_holder import DeployDataHolder
from cloudshell.cp.azure.models.reservation_model import ReservationModel


class AzureModelsParser(object):
    @staticmethod
    def convert_app_resource_to_deployed_app(resource):
        json_str = jsonpickle.decode(resource.app_context.deployed_app_json)
        data_holder = DeployDataHolder(json_str)
        return data_holder

    @staticmethod
    def _set_base_deploy_azure_vm_model_params(deployment_resource_model, data_holder):
        """Set base parameters to the Azure Deploy model

        :param deployment_resource_model: deploy_azure_vm_resource_models.BaseDeployAzureVMResourceModel subclass
        :param data_holder: DeployDataHolder instance
        :return:
        """
        deployment_resource_model.add_public_ip = data_holder.ami_params.add_public_ip
        deployment_resource_model.autoload = data_holder.ami_params.autoload
        deployment_resource_model.cloud_provider = data_holder.ami_params.cloud_provider
        deployment_resource_model.group_name = data_holder.ami_params.group_name
        deployment_resource_model.inbound_ports = data_holder.ami_params.inbound_ports
        deployment_resource_model.instance_type = data_holder.ami_params.instance_type
        deployment_resource_model.public_ip_type = data_holder.ami_params.public_ip_type
        deployment_resource_model.vm_name = data_holder.ami_params.vm_name
        deployment_resource_model.wait_for_ip = data_holder.ami_params.wait_for_ip
        deployment_resource_model.app_name = data_holder.app_name
        deployment_resource_model.username = data_holder.ami_params.username
        deployment_resource_model.password = data_holder.ami_params.password
        deployment_resource_model.extension_script_file = data_holder.ami_params.extension_script_file
        deployment_resource_model.extension_script_configurations = (
            data_holder.ami_params.extension_script_configurations)

    @staticmethod
    def convert_to_deploy_azure_vm_resource_model(deployment_request):
        """Convert deployment request JSON to the DeployAzureVMResourceModel model

        :param deployment_request: (str) JSON string
        :return: deploy_azure_vm_resource_models.DeployAzureVMResourceModel instance
        """
        data = jsonpickle.decode(deployment_request)
        data_holder = DeployDataHolder(data)
        deployment_resource_model = DeployAzureVMResourceModel()
        deployment_resource_model.image_offer = data_holder.ami_params.image_offer
        deployment_resource_model.image_publisher = data_holder.ami_params.image_publisher
        deployment_resource_model.image_sku = data_holder.ami_params.image_sku
        deployment_resource_model.image_version = data_holder.ami_params.image_version
        AzureModelsParser._set_base_deploy_azure_vm_model_params(deployment_resource_model, data_holder)

        return deployment_resource_model

    @staticmethod
    def convert_to_deploy_azure_vm_from_custom_image_resource_model(deployment_request):
        """Convert deployment request JSON to the DeployAzureVMFromCustomImageResourceModel model

        :param deployment_request: (str) JSON string
        :return: deploy_azure_vm_resource_models.DeployAzureVMFromCustomImageResourceModel instance
        """
        data = jsonpickle.decode(deployment_request)
        data_holder = DeployDataHolder(data)
        deployment_resource_model = DeployAzureVMFromCustomImageResourceModel()
        deployment_resource_model.image_urn = data_holder.ami_params.image_urn
        deployment_resource_model.image_os_type = data_holder.ami_params.image_os_type
        AzureModelsParser._set_base_deploy_azure_vm_model_params(deployment_resource_model, data_holder)

        return deployment_resource_model

    @staticmethod
    def convert_to_cloud_provider_resource_model(resource, cloudshell_session):
        """
        :param resource:
        :param cloudshell_session: cloudshell.api.cloudshell_api.CloudShellAPISession instance
        :return: AzureCloudProviderResourceModel
        """
        resource_context = resource.attributes
        azure_resource_model = AzureCloudProviderResourceModel()
        azure_resource_model.azure_client_id = resource_context['Azure Client ID']
        azure_resource_model.azure_subscription_id = resource_context['Azure Subscription ID']
        azure_resource_model.azure_tenant = resource_context['Azure Tenant ID']
        azure_resource_model.instance_type = resource_context['Instance Type']
        azure_resource_model.networks_in_use = resource_context['Networks In Use']
        azure_resource_model.region = resource_context['Region'].replace(" ", "").lower()
        azure_resource_model.management_group_name = resource_context['Management Group Name']

        encrypted_azure_secret = resource_context['Azure Secret']
        azure_secret = cloudshell_session.DecryptPassword(encrypted_azure_secret)
        azure_resource_model.azure_secret = azure_secret.Value

        return azure_resource_model

    @staticmethod
    def convert_to_reservation_model(reservation_context):
        """
        :param ReservationContextDetails reservation_context:
        :rtype: ReservationModel
        """
        return ReservationModel(reservation_context)

    @staticmethod
    def get_public_ip_from_connected_resource_details(resource_context):
        public_ip = ""
        if resource_context.remote_endpoints is not None:
            public_ip = resource_context.remote_endpoints[0].attributes.get("Public IP", public_ip)

        return public_ip

    @staticmethod
    def get_private_ip_from_connected_resource_details(resource_context):
        private_ip = ""
        if resource_context.remote_endpoints is not None:
            private_ip = resource_context.remote_endpoints[0].address

        return private_ip

    @staticmethod
    def get_connected_resource_fullname(resource_context):
        if resource_context.remote_endpoints[0]:
            return resource_context.remote_endpoints[0].fullname
        else:
            raise ValueError('Could not find resource fullname on the deployed app.')
