# WMCore dependecies here
from WMCore.REST.Error import ExecutionError
from WMCore.REST.Server import RESTEntity, restcall, rows
from WMCore.REST.Validation import validate_str, validate_strlist, validate_num, validate_numlist

# CRABServer dependecies here
from CRABInterface.DataWorkflow import DataWorkflow
from CRABInterface.RESTExtensions import authz_owner_match

# external dependecies here
import cherrypy
import re


class RESTWorkflow(RESTEntity):
    """REST entity for workflows and relative subresources"""

    def __init__(self, app, api, config, mount):
        RESTEntity.__init__(self, app, api, config, mount)

        self.workflowmgr = DataWorkflow()

    def validate(self, apiobj, method, api, param, safe):
        """Validating all the input parameter as enforced by the WMCore.REST module"""

        # TODO: we should start replacing most of the regex here with what we have in WMCore.Lexicon
        #       (this probably requires to adapt something on Lexicon)
        if method in ['PUT']:
            validate_str("workflow", param, safe, re.compile("^[a-zA-Z0-9\.\-_]{1,80}$"), optional=False)
            validate_str("jobtype", param, safe, re.compile("^[A-Za-z]*$"), optional=False)
            validate_str("jobsw", param, safe, re.compile("^CMSSW(_\d+){3}(_[a-zA-Z0-9_]+)?$"), optional=False)
            validate_str("jobarch", param, safe, re.compile("^slc[0-9]{1}_[a-z0-9]+_gcc[a-z0-9]+(_[a-z0-9]+)?$"), optional=False)
            validate_str("inputdata", param, safe,
               re.compile("^/(\*|[a-zA-Z\*][a-zA-Z0-9_\*]{0,100})(/(\*|[a-zA-Z0-9_\.\-\*]{1,100})){0,1}(/(\*|[A-Z\-\*]{1,50})){0,1}$"), optional=False)
            validate_strlist("siteblacklist", param, safe, re.compile("^T[0-3%]((_[A-Z]{2}(_[A-Za-z0-9]+)*)?)$"))
            validate_strlist("sitewhitelist", param, safe, re.compile("^T[0-3%]((_[A-Z]{2}(_[A-Za-z0-9]+)*)?)$"))
            validate_str("runwhitelist", param, safe, re.compile("^\d+(-\d+)?(,\d+(-\d+)?)*$"), optional=True) #TODO has it been renamed to RunRange (?);
            validate_str("runblacklist", param, safe, re.compile("^\d+(-\d+)?(,\d+(-\d+)?)*$"), optional=True)
            validate_strlist("blockwhitelist", param, safe, re.compile("^(/[a-zA-Z0-9\.\-_]{1,100}){3}#[a-zA-Z0-9\.\-_]{1,100}$"))
            validate_strlist("blockblacklist", param, safe, re.compile("^(/[a-zA-Z0-9\.\-_]{1,100}){3}#[a-zA-Z0-9\.\-_]{1,100}$"))
            validate_str("splitalgo", param, safe, re.compile("^EventBased|FileBased|LumiBased|RunBased|SizeBased$"), optional=False)
            validate_num("algoargs", param, safe, optional=False)
            validate_str("configdoc", param, safe, re.compile("^[A-Za-z0-9]*$"), optional=False)
            validate_str("userisburl", param, safe, re.compile("^https?://([-\w\.]+)+(:\d+)?(/([\w/_\.]*(\?\S+)?)?)?$"), optional=False)
            validate_strlist("adduserfiles", param, safe, re.compile("^([a-zA-Z0-9\-\._]+)$"))
            validate_strlist("addoutputfiles", param, safe, re.compile("^([a-zA-Z0-9\-\._]+)$"))
            validate_num("savelogsflag", param, safe, optional=False)
            validate_str("publishname", param, safe, re.compile("[a-zA-Z0-9\-_]+"), optional=False)
            validate_str("asyncdest", param, safe, re.compile("^T[0-3%]((_[A-Z]{2}(_[A-Za-z0-9]+)*)?)$"), optional=False)
            validate_str("campaign", param, safe, re.compile("^[a-zA-Z0-9\.\-_]{1,80}$"), optional=True)
            validate_num("blacklistT1", param, safe, optional=False)

        elif method in ['POST']:
            validate_str("workflow", param, safe, re.compile("^[a-zA-Z0-9\.\-_]{1,100}$"), optional=False)
            validate_num("resubmit", param, safe, optional=True)
            validate_str("dbsurl", param, safe, re.compile("^https?://([-\w\.]+)+(:\d+)?(/([\w/_\.]*(\?\S+)?)?)?$"), optional=True)

        elif method in ['GET']:
            validate_strlist("workflow", param, safe, re.compile("^[a-zA-Z0-9\.\-_]{1,100}$"))
            validate_str('subresource', param, safe, re.compile("^errors|report|logs|data|schema|configcache$"), optional=True)
            #XXX: parameters of subresources calls has to be put here
            #used by get latest
            validate_num('age', param, safe, optional=True)
            #used by get log, gt data
            validate_num('limit', param, safe, optional=True)
            #used by errors
            validate_num('shortformat', param, safe, optional=True)

        elif method in ['DELETE']:
            validate_strlist("workflow", param, safe, re.compile("^[a-zA-Z0-9\.\-_]{1,100}$"))
            validate_num("force", param, safe, optional=True)


    @restcall
    def put(self, workflow, jobtype, jobsw, jobarch, inputdata, siteblacklist, sitewhitelist, runwhitelist, runblacklist, blockwhitelist, blockblacklist,
            splitalgo, algoargs, configdoc, userisburl, adduserfiles, addoutputfiles, savelogsflag, publishname, asyncdest, campaign, blacklistT1):
        """Insert a new workflow. The caller needs to be a CMS user with a valid CMS x509 cert/proxy.

           :arg str workflow: workflow name requested by the user;
           :arg str jobtype: job type of the workflow, usally CMSSW;
           :arg str jobsw: software requirement;
           :arg str jobarch: software architecture (=SCRAM_ARCH);
           :arg str list inputdata: input datasets;
           :arg str list siteblacklist: black list of sites, with CMS name;
           :arg str list sitewhitelist: white list of sites, with CMS name;
           :arg str asyncdest: CMS site name for storage destination of the output files;
           :arg int list runwhitelist: selective list of input run from the specified input dataset;
           :arg int list runblacklist:  input run to be excluded from the specified input dataset;
           :arg str list blockwhitelist: selective list of input iblock from the specified input dataset;
           :arg str list blockblacklist:  input blocks to be excluded from the specified input dataset;
           :arg str splitalgo: algorithm to be used for the workflow splitting;
           :arg str algoargs: argument to be used by the splitting algorithm;
           :arg str configdoc: the document id of the config cache document:
           :arg str userisburl: URL of the input sandbox file;
           :arg str list adduserfiles: list of additional input files;
           :arg str list addoutputfiles: list of additional output files;
           :arg int savelogsflag: archive the log files? 0 no, everything else yes;
           :arg str publishname: name to use for data publication;
           :arg str asyncdest: final destination of workflow output files;
           :arg str campaign: needed just in case the workflow has to be appended to an existing campaign;
           :arg str userdn: the user DN
           :arg str configfile: configuration file provided by the user as string
           :arg str psettweaks: a json representing the psettweak provided by the user
           :arg str psethash: the hash od the psetfile
           :arg str label:
           :arg str  description:

           :returns: a dict which contaians details of the request"""

        return self.workflowmgr.submit(workflow=workflow, jobtype=jobtype, jobsw=jobsw, jobarch=jobarch, inputdata=inputdata,
                                      siteblacklist=siteblacklist, sitewhitelist=sitewhitelist, runwhitelist=runwhitelist,
                                      runblacklist=runblacklist, blockwhitelist=blockwhitelist, blockblacklist=blockblacklist,
                                      splitalgo=splitalgo, algoargs=algoargs, configdoc=configdoc, userisburl=userisburl,
                                      adduserfiles=adduserfiles, addoutputfiles=addoutputfiles, savelogsflag=savelogsflag,
                                      userdn=cherrypy.request.user['dn'], userhn=cherrypy.request.user['login'],
                                      publishname=publishname, asyncdest=asyncdest, campaign=campaign, blacklistT1=blacklistT1)

    @restcall
    def post(self, workflow, resubmit, dbsurl):
        """Modifies an existing workflow. The caller needs to be a CMS user owner of the workflow.

           :arg str workflow: unique name identifier of the workflow;
           :arg int resubmit: reubmit the workflow? 0 no, everything else yes;
           :arg str dbsurl: publish the workflow results
           :returns: return the modified fields or the publication details"""

        result = []
        if resubmit:
            # strict check on authz: only the workflow owner can modify it
            alldocs = authz_owner_match(self.workflowmgr.database, [workflow])
            result = rows([self.workflowmgr.resubmit(workflow)])
        elif dbsurl:
            result = rows([self.workflowmgr.publish(workflow, dbsurl)])

        return result

    @restcall
    def get(self, workflow, subresource, age, limit, shortformat):
        """Retrieves the workflows information, like a status summary, in case the workflow unique name is specified.
           Otherwise returns all workflows since (now - age) for which the user is the owner.
           The caller needs to be a CMS user owner of the workflow.

           :arg str list workflow: list of unique name identifiers of workflows;
           :arg int age: max workflows age in days;
           :arg str subresource: the specific workflow information to be accessed;
           :arg int limit: limit of return entries for some specific subresource;
           :retrun: the list of workflows with the relative status summary in case of per user request; or
                    the requested subresource."""

        result = []
        if workflow:
            # if have the wf then retrieve the wf status summary
            if not subresource:
                return self.workflowmgr.status(workflow)
            # if have a subresource then it should be one of these
            elif subresource == 'logs':
                result = self.workflowmgr.logs(workflow, limit)
            elif subresource == 'data':
                result = self.workflowmgr.output(workflow, limit)
            elif subresource == 'errors':
                result = self.workflowmgr.errors(workflow, shortformat)
            elif subresource == 'report':
                result = rows([self.workflowmgr.report(workflow)])
            elif subresource == 'schema':
                result = rows([self.workflowmgr.schema(workflow)])
            elif subresource == 'configcache':
                result = rows([self.workflowmgr.configcache(workflow)])
            # if here means that no valid subresource has been requested
            # flow should never pass through here since validation restrict this
            else:
                raise ExecutionError("Validation or method error")
        else:
            # retrieve the information about latest worfklows for that user
            # age can have a default: 1 week ?
            cherrypy.log("Found user '%s'" % cherrypy.request.user['login'])
            result = self.workflowmgr.getLatests(cherrypy.request.user['login'], limit, age)

        return result

    @restcall
    def delete(self, workflow, force):
        """Aborts a workflow. The user needs to be a CMS owner of the workflow.

           :arg str list workflow: list of unique name identifiers of workflows;
           :arg int force: force to delete the workflows in any case; 0 no, everything else yes;
           :return: nothing?"""

        # strict check on authz: only the workflow owner can modify it
        alldocs = authz_owner_match(self.workflowmgr.database, workflow)
        result = rows([self.workflowmgr.kill(workflow, force)])
        return result
