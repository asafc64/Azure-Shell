import jsonpickle
from threading import Lock

from cloudshell.core.context.error_handling_context import ErrorHandlingContext
from cloudshell.shell.core.session.cloudshell_session import CloudShellSessionContext
from cloudshell.cp.azure.common.deploy_data_holder import DeployDataHolder
from cloudshell.cp.azure.domain.context.validators_factory_context import ValidatorsFactoryContext
from cloudshell.cp.azure.domain.services.cryptography_service import CryptographyService
from cloudshell.cp.azure.domain.services.lock_service import GenericLockProvider
from cloudshell.cp.azure.domain.services.tags import TagService
from cloudshell.cp.azure.domain.vm_management.operations.access_key_operation import AccessKeyOperation
from cloudshell.cp.azure.domain.vm_management.operations.delete_operation import DeleteAzureVMOperation
from cloudshell.shell.core.session.logging_session import LoggingSessionContext
from cloudshell.cp.azure.domain.services.network_service import NetworkService
from cloudshell.cp.azure.domain.services.parsers.azure_model_parser import AzureModelsParser
from cloudshell.cp.azure.domain.services.parsers.azure_resource_id_parser import AzureResourceIdParser
from cloudshell.cp.azure.domain.services.parsers.command_result_parser import CommandResultsParser
from cloudshell.cp.azure.domain.services.virtual_machine_service import VirtualMachineService
from cloudshell.cp.azure.domain.services.storage_service import StorageService
from cloudshell.cp.azure.domain.services.vm_credentials_service import VMCredentialsService
from cloudshell.cp.azure.domain.services.key_pair import KeyPairService
from cloudshell.cp.azure.domain.services.security_group import SecurityGroupService
from cloudshell.cp.azure.domain.services.name_provider import NameProviderService
from cloudshell.cp.azure.domain.services.vm_extension import VMExtensionService
from cloudshell.cp.azure.domain.vm_management.operations.deploy_operation import DeployAzureVMOperation
from cloudshell.cp.azure.domain.vm_management.operations.power_operation import PowerAzureVMOperation
from cloudshell.cp.azure.domain.vm_management.operations.refresh_ip_operation import RefreshIPOperation
from cloudshell.cp.azure.domain.vm_management.operations.prepare_connectivity_operation import \
    PrepareConnectivityOperation
from cloudshell.cp.azure.common.azure_clients import AzureClientsManager
from cloudshell.cp.azure.domain.services.parsers.custom_param_extractor import VmCustomParamsExtractor
from cloudshell.cp.azure.domain.vm_management.operations.app_ports_operation import DeployedAppPortsOperation


class AzureShell(object):
    def __init__(self):
        self.command_result_parser = CommandResultsParser()
        self.model_parser = AzureModelsParser()
        self.resource_id_parser = AzureResourceIdParser()
        self.vm_service = VirtualMachineService()
        self.network_service = NetworkService()
        self.storage_service = StorageService()
        self.tags_service = TagService()
        self.vm_credentials_service = VMCredentialsService()
        self.key_pair_service = KeyPairService(storage_service=self.storage_service)
        self.security_group_service = SecurityGroupService(self.network_service)
        self.vm_custom_params_extractor = VmCustomParamsExtractor()
        self.cryptography_service = CryptographyService()
        self.name_provider_service = NameProviderService()
        self.vm_extension_service = VMExtensionService()
        self.access_key_operation = AccessKeyOperation(self.key_pair_service, self.storage_service)
        self.generic_lock_provider = GenericLockProvider()
        self.subnet_locker = Lock()

        self.prepare_connectivity_operation = PrepareConnectivityOperation(
            vm_service=self.vm_service,
            network_service=self.network_service,
            storage_service=self.storage_service,
            tags_service=self.tags_service,
            key_pair_service=self.key_pair_service,
            security_group_service=self.security_group_service,
            cryptography_service=self.cryptography_service,
            name_provider_service=self.name_provider_service,
            subnet_locker=self.subnet_locker)

        self.deploy_azure_vm_operation = DeployAzureVMOperation(
            vm_service=self.vm_service,
            network_service=self.network_service,
            storage_service=self.storage_service,
            key_pair_service=self.key_pair_service,
            tags_service=self.tags_service,
            vm_credentials_service=self.vm_credentials_service,
            security_group_service=self.security_group_service,
            name_provider_service=self.name_provider_service,
            vm_extension_service=self.vm_extension_service,
            generic_lock_provider=self.generic_lock_provider)

        self.power_vm_operation = PowerAzureVMOperation(vm_service=self.vm_service)

        self.refresh_ip_operation = RefreshIPOperation(vm_service=self.vm_service,
                                                       resource_id_parser=self.resource_id_parser)

        self.delete_azure_vm_operation = DeleteAzureVMOperation(
            vm_service=self.vm_service,
            network_service=self.network_service,
            tags_service=self.tags_service,
            security_group_service=self.security_group_service,
            storage_service=self.storage_service,
            generic_lock_provider=self.generic_lock_provider,
            subnet_locker=self.subnet_locker)

        self.deployed_app_ports_operation = DeployedAppPortsOperation(
            vm_custom_params_extractor=self.vm_custom_params_extractor)

    def deploy_azure_vm(self, command_context, deployment_request):
        """Will deploy Azure Image on the cloud provider

        :param ResourceCommandContext command_context:
        :param JSON Obj deployment_request:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info('Deploying Azure VM...')

                azure_vm_deployment_model = self.model_parser.convert_to_deploy_azure_vm_resource_model(
                    deployment_request)

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                        resource=command_context.resource,
                        cloudshell_session=cloudshell_session)

                    if azure_vm_deployment_model.password:
                        logger.info('Decrypting Azure VM password...')
                        decrypted_pass = cloudshell_session.DecryptPassword(azure_vm_deployment_model.password)
                        azure_vm_deployment_model.password = decrypted_pass.Value

                azure_clients = AzureClientsManager(cloud_provider_model)
                reservation = self.model_parser.convert_to_reservation_model(command_context.reservation)

                with ValidatorsFactoryContext() as validator_factory:
                    deploy_data = self.deploy_azure_vm_operation.deploy(
                        azure_vm_deployment_model=azure_vm_deployment_model,
                        cloud_provider_model=cloud_provider_model,
                        reservation=reservation,
                        network_client=azure_clients.network_client,
                        compute_client=azure_clients.compute_client,
                        storage_client=azure_clients.storage_client,
                        validator_factory=validator_factory,
                        logger=logger)

                    logger.info('End deploying Azure VM')
                    return self.command_result_parser.set_command_result(deploy_data)

    def deploy_vm_from_custom_image(self, command_context, deployment_request):
        """Deploy Azure Image from given Image URN

        :param command_context: ResourceCommandContext instance
        :param deployment_request: (str) JSON string
        :return:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info('Deploying Azure VM From Custom Image...')

                azure_vm_deployment_model = (
                    self.model_parser.convert_to_deploy_azure_vm_from_custom_image_resource_model(deployment_request))
                reservation = self.model_parser.convert_to_reservation_model(command_context.reservation)

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                        resource=command_context.resource,
                        cloudshell_session=cloudshell_session)

                    if azure_vm_deployment_model.password:
                        logger.info('Decrypting Azure VM password...')
                        decrypted_pass = cloudshell_session.DecryptPassword(azure_vm_deployment_model.password)
                        azure_vm_deployment_model.password = decrypted_pass.Value

                azure_clients = AzureClientsManager(cloud_provider_model)

                with ValidatorsFactoryContext() as validator_factory:
                    deploy_data = self.deploy_azure_vm_operation.deploy_from_custom_image(
                        azure_vm_deployment_model=azure_vm_deployment_model,
                        cloud_provider_model=cloud_provider_model,
                        reservation=reservation,
                        network_client=azure_clients.network_client,
                        compute_client=azure_clients.compute_client,
                        storage_client=azure_clients.storage_client,
                        validator_factory=validator_factory,
                        logger=logger)

                    logger.info('End deploying Azure VM From Custom Image')
                    return self.command_result_parser.set_command_result(deploy_data)

    def prepare_connectivity(self, context, request):
        """
        Creates a connectivity for the Sandbox:
        1.Resource group
        2.Storage account
        3.Key pair
        4.Network Security Group
        5.Creating a subnet under the

        :param context:
        :param request:
        :return:
        """
        with LoggingSessionContext(context) as logger:
            with ErrorHandlingContext(logger):
                logger.info('Preparing Connectivity for Azure VM...')

                with CloudShellSessionContext(context) as cloudshell_session:
                    cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                        resource=context.resource,
                        cloudshell_session=cloudshell_session)

                azure_clients = AzureClientsManager(cloud_provider_model)

                prepare_connectivity_request = DeployDataHolder(jsonpickle.decode(request))
                prepare_connectivity_request = getattr(prepare_connectivity_request, 'driverRequest', None)

                result = self.prepare_connectivity_operation.prepare_connectivity(
                    reservation=self.model_parser.convert_to_reservation_model(context.reservation),
                    cloud_provider_model=cloud_provider_model,
                    storage_client=azure_clients.storage_client,
                    resource_client=azure_clients.resource_client,
                    network_client=azure_clients.network_client,
                    logger=logger,
                    request=prepare_connectivity_request)

                logger.info('End Preparing Connectivity for Azure VM')
                return self.command_result_parser.set_command_result({'driverResponse': {'actionResults': result}})

    def cleanup_connectivity(self, command_context):
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info('Teardown...')

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                        resource=command_context.resource,
                        cloudshell_session=cloudshell_session)

                azure_clients = AzureClientsManager(cloud_provider_model)
                resource_group_name = command_context.reservation.reservation_id

                self.generic_lock_provider.remove_lock_resource(resource_group_name, logger=logger)

                result = self.delete_azure_vm_operation.cleanup_connectivity(
                    network_client=azure_clients.network_client,
                    resource_client=azure_clients.resource_client,
                    cloud_provider_model=cloud_provider_model,
                    resource_group_name=resource_group_name,
                    logger=logger)

                logger.info('End Teardown')
                return self.command_result_parser.set_command_result({'driverResponse': {'actionResults': [result]}})

    def delete_azure_vm(self, command_context):
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info('Deleting Azure VM...')

                data_holder = self.model_parser.convert_app_resource_to_deployed_app(
                    command_context.remote_endpoints[0])
                resource_group_name = next(o.value for o in
                                           data_holder.vmdetails.vmCustomParams if o.name == 'resource_group')

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                        resource=command_context.resource,
                        cloudshell_session=cloudshell_session)

                azure_clients = AzureClientsManager(cloud_provider_model)
                vm_name = command_context.remote_endpoints[0].fullname

                self.delete_azure_vm_operation.delete(
                    compute_client=azure_clients.compute_client,
                    network_client=azure_clients.network_client,
                    storage_client=azure_clients.storage_client,
                    group_name=resource_group_name,
                    vm_name=vm_name,
                    logger=logger)

                logger.info('End Deleting Azure VM')

    def power_on_vm(self, command_context):
        """Power on Azure VM

        :param ResourceCommandContext command_context:
        :return:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info('Starting power on operation on Azure VM...')

                reservation = self.model_parser.convert_to_reservation_model(command_context.remote_reservation)
                group_name = reservation.reservation_id

                resource = command_context.remote_endpoints[0]
                data_holder = self.model_parser.convert_app_resource_to_deployed_app(resource)
                vm_name = data_holder.name

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                        resource=command_context.resource,
                        cloudshell_session=cloudshell_session)

                azure_clients = AzureClientsManager(cloud_provider_model)

                self.power_vm_operation.power_on(compute_client=azure_clients.compute_client,
                                                 resource_group_name=group_name,
                                                 vm_name=vm_name)

                logger.info('Azure VM {} was successfully powered on'.format(vm_name))

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloudshell_session.SetResourceLiveStatus(resource.fullname, "Online", "Active")

    def power_off_vm(self, command_context):
        """Power off Azure VM

        :param ResourceCommandContext command_context:
        :return:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info('Starting power off operation on Azure VM...')

                reservation = self.model_parser.convert_to_reservation_model(command_context.remote_reservation)
                group_name = reservation.reservation_id

                resource = command_context.remote_endpoints[0]
                data_holder = self.model_parser.convert_app_resource_to_deployed_app(resource)
                vm_name = data_holder.name

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                        resource=command_context.resource,
                        cloudshell_session=cloudshell_session)

                azure_clients = AzureClientsManager(cloud_provider_model)

                self.power_vm_operation.power_off(compute_client=azure_clients.compute_client,
                                                  resource_group_name=group_name,
                                                  vm_name=vm_name)

                logger.info('Azure VM {} was successfully powered off'.format(vm_name))

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloudshell_session.SetResourceLiveStatus(resource.fullname, "Offline", "Powered Off")

    def refresh_ip(self, command_context):
        """Refresh private and public IPs on the Cloudshell resource

        :param ResourceRemoteCommandContext command_context:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info("Starting Refresh IP operation...")

                reservation = self.model_parser.convert_to_reservation_model(command_context.remote_reservation)
                resource = command_context.remote_endpoints[0]
                data_holder = self.model_parser.convert_app_resource_to_deployed_app(resource)
                vm_name = data_holder.name
                group_name = reservation.reservation_id
                private_ip = self.model_parser.get_private_ip_from_connected_resource_details(command_context)
                public_ip = self.model_parser.get_public_ip_from_connected_resource_details(command_context)
                resource_fullname = self.model_parser.get_connected_resource_fullname(command_context)

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                        resource=command_context.resource,
                        cloudshell_session=cloudshell_session)

                azure_clients = AzureClientsManager(cloud_provider_model)

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    self.refresh_ip_operation.refresh_ip(cloudshell_session=cloudshell_session,
                                                         compute_client=azure_clients.compute_client,
                                                         network_client=azure_clients.network_client,
                                                         resource_group_name=group_name,
                                                         vm_name=vm_name,
                                                         private_ip_on_resource=private_ip,
                                                         public_ip_on_resource=public_ip,
                                                         resource_fullname=resource_fullname,
                                                         logger=logger)

                logger.info('Azure VM IPs were successfully refreshed'.format(vm_name))

    def get_access_key(self, command_context):
        """
        Returns public key
        :param ResourceRemoteCommandContext command_context:
        :rtype str:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info("Starting GetAccessKey...")

                with CloudShellSessionContext(command_context) as cloudshell_session:
                    cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                        resource=command_context.resource,
                        cloudshell_session=cloudshell_session)

                azure_clients = AzureClientsManager(cloud_provider_model)

                with ValidatorsFactoryContext() as validator_factory:
                    resource_group_name = command_context.remote_reservation.reservation_id

                    return self.access_key_operation.get_access_key(storage_client=azure_clients.storage_client,
                                                                    group_name=resource_group_name,
                                                                    validator_factory=validator_factory)

    def get_application_ports(self, command_context):
        """Get application ports in a nicely formatted manner

        :param command_context: ResourceRemoteCommandContext
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info('Getting Application Ports...')
                resource = command_context.remote_endpoints[0]
                data_holder = self.model_parser.convert_app_resource_to_deployed_app(resource)

                return self.deployed_app_ports_operation.get_formated_deployed_app_ports(
                    data_holder.vmdetails.vmCustomParams)
